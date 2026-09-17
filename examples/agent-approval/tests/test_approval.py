import concurrent.futures
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

# Local API tests must not inherit system HTTP proxies.
def urlopen(request):
    return build_opener(ProxyHandler({})).open(request, timeout=5)

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from approval import ApprovalService, ApprovalError, BASE, SCENARIOS, AGENTS, destination
from build_rules import build
from server import create_server

class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.now=1_800_000_000.0
        self.s=ApprovalService(clock=lambda:self.now)

    def tearDown(self):
        self.s.close()

    def request(self,**kw):
        return dict(BASE,**kw)

    def authorize(self,request):
        r=self.s.evaluate(request)
        self.assertNotEqual(r['state'],'blocked')
        for role in r['decision']['required_roles']:
            user={'owner':'lin','security':'chen','finance':'zhou'}[role]
            r=self.s.review(r['id'],user,'已检查演示业务用途，同意本次操作。')
        self.assertEqual(r['state'],'authorized')
        return r

    def fail_code(self,code,call):
        with self.assertRaises(ApprovalError) as exc:
            call()
        self.assertEqual(exc.exception.code,code)

    def check(self,request,key):
        return next(x for x in self.s.evaluate(request)['decision']['checks'] if x['key']==key)

    def test_redaction_happens_at_execution(self):
        request=SCENARIOS[1]['request']
        r=self.authorize(request)
        receipt=self.s.execute(r['id'],r['grant_token'],request)['receipt']
        self.assertTrue(receipt['redacted'])
        self.assertNotIn('customer@example.test',receipt['effective_payload'])
        self.assertNotIn('13800138000',receipt['effective_payload'])
        self.assertIn('演示设备',receipt['effective_payload'])
        self.assertEqual(receipt['target'],'sales@partner.example')

    def test_false_public_label_cannot_hide_secret(self):
        r=self.s.evaluate(self.request(action='send_email',target='user@partner.example',data_class='public',payload='API_KEY=sk_demo_FAKE'))
        self.assertEqual(r['decision']['facts']['classification'],'secret')
        self.assertEqual(r['state'],'blocked')
        self.assertIsNone(r['grant_token'])

    def test_false_public_label_cannot_hide_pii(self):
        r=self.s.evaluate(self.request(action='send_email',target='user@partner.example',data_class='public',payload='Email: user@example.test'))
        self.assertEqual(r['decision']['outcome'],'redact')

    def test_multi_reviewer_requires_both_roles(self):
        request=SCENARIOS[5]['request']
        r=self.s.evaluate(request)
        self.assertEqual(r['decision']['required_roles'],['finance','security'])
        r=self.s.review(r['id'],'zhou','已核对演示预算。')
        self.assertEqual(r['state'],'pending')
        self.assertIsNone(r['grant_token'])
        self.fail_code('NOT_AUTHORIZED',lambda:self.s.execute(r['id'],'',request))
        r=self.s.review(r['id'],'chen','已核对模拟接口权限。')
        self.assertEqual(r['state'],'authorized')
        self.assertTrue(self.s.execute(r['id'],r['grant_token'],request)['receipt']['simulated'])

    def test_requester_cannot_approve(self):
        r=self.s.evaluate(SCENARIOS[2]['request'])
        self.fail_code('WRONG_ROLE',lambda:self.s.review(r['id'],'requester','尝试自我审批操作。'))
        self.assertEqual(self.s.state()['requests'][0]['state'],'pending')
        self.assertEqual(self.s.state()['events'][-1]['kind'],'审批拒绝')

    def test_wrong_role_cannot_approve(self):
        r=self.s.evaluate(SCENARIOS[2]['request'])
        self.fail_code('WRONG_ROLE',lambda:self.s.review(r['id'],'zhou','财务尝试批准收件人。'))

    def test_duplicate_role_not_counted_twice(self):
        r=self.s.evaluate(SCENARIOS[5]['request'])
        self.s.review(r['id'],'zhou','已核对模拟预算。')
        self.fail_code('ALREADY_REVIEWED',lambda:self.s.review(r['id'],'zhou','再次批准同一申请。'))

    def test_rejected_request_never_executes(self):
        request=SCENARIOS[2]['request'];r=self.s.evaluate(request)
        r=self.s.review(r['id'],'lin','业务理由不充分，驳回。',False)
        self.assertEqual(r['state'],'rejected')
        self.fail_code('NOT_AUTHORIZED',lambda:self.s.execute(r['id'],'',request))

    def test_block_cannot_be_overridden(self):
        r=self.s.evaluate(SCENARIOS[4]['request'])
        self.fail_code('NOT_PENDING',lambda:self.s.review(r['id'],'chen','尝试批准被禁止的操作。'))

    def test_expired_grant_revoked(self):
        r=self.authorize(BASE);self.now+=301
        self.fail_code('EXPIRED',lambda:self.s.execute(r['id'],r['grant_token'],BASE))
        self.assertEqual(self.s.state()['requests'][0]['state'],'revoked')

    def test_expired_pending_request_cannot_be_approved(self):
        r=self.s.evaluate(SCENARIOS[2]['request']);self.now+=301
        self.fail_code('EXPIRED',lambda:self.s.review(r['id'],'lin','已核对，但申请已经过期。'))

    def test_exact_expiry_boundary(self):
        r=self.authorize(BASE);self.now+=300
        self.fail_code('EXPIRED',lambda:self.s.execute(r['id'],r['grant_token'],BASE))

    def test_invalid_token_does_not_consume_valid_grant(self):
        r=self.authorize(BASE)
        self.fail_code('INVALID_GRANT',lambda:self.s.execute(r['id'],'wrong',BASE))
        self.assertTrue(self.s.execute(r['id'],r['grant_token'],BASE)['receipt']['simulated'])

    def test_token_cannot_be_used_for_another_request(self):
        a=self.authorize(BASE);b=self.authorize(BASE)
        self.fail_code('INVALID_GRANT',lambda:self.s.execute(b['id'],a['grant_token'],BASE))

    def test_single_use(self):
        r=self.authorize(BASE)
        self.s.execute(r['id'],r['grant_token'],BASE)
        self.fail_code('ALREADY_EXECUTED',lambda:self.s.execute(r['id'],r['grant_token'],BASE))
        self.assertEqual(len(self.s.state()['receipts']),1)

    def test_concurrent_execution_is_atomic(self):
        r=self.authorize(BASE)
        def execute():
            try:
                self.s.execute(r['id'],r['grant_token'],BASE)
                return 'ok'
            except ApprovalError as e:
                return e.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            result=list(pool.map(lambda _:execute(),range(2)))
        self.assertCountEqual(result,['ok','ALREADY_EXECUTED'])
        self.assertEqual(len(self.s.state()['receipts']),1)

    def test_policy_switch_revokes_grants_and_pending(self):
        r=self.authorize(BASE);p=self.s.evaluate(SCENARIOS[2]['request'])
        self.s.switch_policy('v2')
        self.assertTrue(all(x['state']=='revoked' for x in self.s.state()['requests']))
        self.fail_code('NOT_AUTHORIZED',lambda:self.s.execute(r['id'],r['grant_token'],BASE))
        self.fail_code('NOT_PENDING',lambda:self.s.review(p['id'],'lin','规则更新后尝试批准。'))

    def test_policy_switch_back_does_not_revive_grant(self):
        r=self.authorize(BASE)
        self.s.switch_policy('v2');self.s.switch_policy('v1')
        self.fail_code('NOT_AUTHORIZED',lambda:self.s.execute(r['id'],r['grant_token'],BASE))

    def test_same_policy_keeps_grant(self):
        r=self.authorize(BASE);self.s.switch_policy('v1')
        self.s.execute(r['id'],r['grant_token'],BASE)

    def test_preexecution_rate_is_rechecked(self):
        old=self.authorize(BASE)
        for _ in range(10):
            r=self.authorize(BASE);self.s.execute(r['id'],r['grant_token'],BASE)
        self.fail_code('RISK_CHANGED',lambda:self.s.execute(old['id'],old['grant_token'],BASE))
        self.assertEqual(len(self.s.state()['receipts']),10)

    def test_rate_limit_counts_only_executions(self):
        for _ in range(25): self.s.evaluate(BASE)
        self.assertEqual(self.s.evaluate(BASE)['decision']['facts']['executions_hour'],0)

    def test_hard_rate_limit_at_twenty(self):
        for _ in range(20):
            r=self.authorize(BASE);self.s.execute(r['id'],r['grant_token'],BASE)
        r=self.s.evaluate(BASE)
        self.assertEqual(r['decision']['outcome'],'deny')
        self.assertEqual(r['decision']['facts']['executions_hour'],20)

    def test_rate_window_expires(self):
        for _ in range(10):
            r=self.authorize(BASE);self.s.execute(r['id'],r['grant_token'],BASE)
        self.now+=3601
        self.assertEqual(self.s.evaluate(BASE)['decision']['outcome'],'allow')

    def test_cumulative_budget_at_execution(self):
        request=self.request(cost=400)
        a=self.authorize(request);b=self.authorize(request);c=self.authorize(request)
        self.s.execute(a['id'],a['grant_token'],request)
        self.s.execute(b['id'],b['grant_token'],request)
        self.fail_code('RISK_CHANGED',lambda:self.s.execute(c['id'],c['grant_token'],request))

    def test_audit_chain_valid(self):
        r=self.authorize(BASE);self.s.execute(r['id'],r['grant_token'],BASE)
        state=self.s.state()
        self.assertTrue(state['audit_valid'])
        self.assertEqual(state['audit_count'],3)
        self.assertNotIn(r['grant_token'],json.dumps(state))

    def test_audit_detects_tampering(self):
        self.s.evaluate(BASE)
        with self.s.db: self.s.db.execute("UPDATE audit SET kind='edited' WHERE seq=1")
        self.assertFalse(self.s.state()['audit_valid'])

    def test_audit_records_execution_rejections(self):
        r=self.authorize(BASE)
        self.fail_code('CONTENT_CHANGED',lambda:self.s.execute(r['id'],r['grant_token'],self.request(target='other.company.example')))
        self.assertEqual(self.s.state()['events'][-1]['detail']['code'],'CONTENT_CHANGED')
        self.assertTrue(self.s.state()['audit_valid'])

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'test.sqlite'
            first=ApprovalService(path,clock=lambda:self.now)
            r=first.evaluate(BASE);first.close()
            second=ApprovalService(path,clock=lambda:self.now)
            try:
                second.execute(r['id'],r['grant_token'],BASE)
                self.assertEqual(second.state()['counts']['executed'],1)
                self.assertTrue(second.state()['audit_valid'])
            finally: second.close()

    def test_generated_graph_matches_checked_in(self):
        path=Path(__file__).resolve().parents[1]/'rules'/'agent-approval.json'
        self.assertEqual(json.loads(path.read_text()),build())

    def test_all_eight_checks_preserved_on_denial(self):
        r=self.s.evaluate(SCENARIOS[4]['request'])
        self.assertEqual(len(r['decision']['checks']),8)
        self.assertTrue(any(c['severity']==4 for c in r['decision']['checks']))

    def test_fingerprint_deterministic(self):
        a=self.s.evaluate(BASE);b=self.s.evaluate(dict(reversed(list(BASE.items()))))
        self.assertEqual(a['fingerprint'],b['fingerprint'])
        self.assertNotEqual(a['grant_token'],b['grant_token'])

    def test_unknown_version_rejected(self):
        self.fail_code('INVALID_VERSION',lambda:self.s.switch_policy('v999'))

    def test_unknown_request_rejected(self):
        self.fail_code('NOT_FOUND',lambda:self.s.review('missing','lin','尝试不存在的申请。'))

    def test_blank_review_note_rejected(self):
        r=self.s.evaluate(SCENARIOS[2]['request'])
        self.fail_code('REVIEW_NOTE',lambda:self.s.review(r['id'],'lin','好'))

    def test_unknown_reviewer_rejected(self):
        r=self.s.evaluate(SCENARIOS[2]['request'])
        self.fail_code('INVALID_REVIEWER',lambda:self.s.review(r['id'],'admin','未知角色不能审批。'))


def add_test(name,fn):
    setattr(ApprovalTests,'test_'+name,fn)

for version in ['v1','v2']:
    for item in SCENARIOS:
        def case(self,item=item,version=version):
            self.s.switch_policy(version)
            expected='review' if version=='v2' and item['id']=='version' else item['expected']
            self.assertEqual(self.s.evaluate(item['request'])['decision']['outcome'],expected)
        add_test('scenario_'+version+'_'+item['id'].replace('-','_'),case)

for agent in AGENTS:
    for action in ['read_file','send_email','update_record','delete_records','http_request']:
        def case(self,agent=agent,action=action):
            target='a@company.example' if action=='send_email' else 'https://api.company.example/x' if action=='http_request' else BASE['target']
            c=self.check(self.request(agent=agent,action=action,target=target),'identity')
            expected=4 if not AGENTS[agent]['active'] or action not in AGENTS[agent]['actions'] else 3 if action=='delete_records' else 1
            self.assertEqual(c['severity'],expected)
        add_test('scope_'+agent+'_'+action,case)

for kind in ['public','internal','customer','secret']:
    for dest in ['company.example','partner.example','new.example','blocked.example']:
        def case(self,kind=kind,dest=dest):
            c=self.check(self.request(action='send_email',target='a@'+dest,data_class=kind),'data')
            expected=1 if kind=='public' or (dest=='company.example' and kind!='secret') else 4 if kind=='secret' and dest!='company.example' else 3
            self.assertEqual(c['severity'],expected)
        add_test('classification_'+kind+'_'+dest.replace('.','_'),case)

for version,threshold in [('v1',100),('v2',50)]:
    for records in [1,49,50,51,99,100,101,1000,1001]:
        def case(self,version=version,threshold=threshold,records=records):
            self.s.switch_policy(version)
            c=self.check(self.request(action='update_record',records=records),'volume')
            self.assertEqual(c['severity'],4 if records>1000 else 3 if records>threshold else 1)
        add_test(f'volume_{version}_{records}',case)

for cost in [0,1,99.99,100,100.01,499.99,500,500.01]:
    def case(self,cost=cost):
        c=self.check(self.request(cost=cost),'budget')
        self.assertEqual(c['severity'],4 if cost>500 else 3 if cost>100 else 1)
    add_test('budget_'+str(cost).replace('.','_'),case)

mutations={'agent':'research','environment':'production','action':'update_record','data_class':'internal','target':'other.company.example','records':2,'cost':1,'payload':'修改后的执行内容。','purpose':'另一个完全不同的业务理由','ticket':'CHG-OTHER'}
for field,value in mutations.items():
    def case(self,field=field,value=value):
        r=self.authorize(BASE)
        self.fail_code('CONTENT_CHANGED',lambda:self.s.execute(r['id'],r['grant_token'],self.request(**{field:value})))
        self.assertEqual(len(self.s.state()['receipts']),0)
        self.assertEqual(self.s.state()['requests'][0]['state'],'revoked')
    add_test('tamper_'+field,case)

invalid=[('records',0),('records',-1),('records',1.5),('records',True),('records','3'),('records',100001),('cost',-1),('cost',float('nan')),('cost',float('inf')),('cost',True),('cost',1000001),('agent','unknown'),('agent',[]),('environment','unknown'),('action','shell'),('data_class','invalid'),('target',''),('target','x\ny'),('target','x'*301),('purpose',None),('payload',{}),('payload','a'*15001),('ticket','a'*121)]
for i,(field,value) in enumerate(invalid):
    def case(self,field=field,value=value):
        self.fail_code('INVALID_INPUT',lambda:self.s.evaluate(self.request(**{field:value})))
    add_test(f'invalid_{i}_{field}',case)

for field in list(BASE)+['extra']:
    def case(self,field=field):
        data=dict(BASE)
        if field=='extra':data['facts']={'scope_allowed':True}
        else:del data[field]
        self.fail_code('INVALID_INPUT',lambda:self.s.evaluate(data))
    add_test('schema_'+field,case)

for target,expected in [('company.example','internal'),('a.company.example','internal'),('company.example.evil.test','external'),('partner.example.evil.test','external'),('a@PARTNER.EXAMPLE','trusted'),('a@blocked.example','blocked'),('https://company.example@evil.test/x','external')]:
    def case(self,target=target,expected=expected):
        self.assertEqual(destination(target),expected)
    add_test('destination_'+str(len(ApprovalTests.__dict__)),case)

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.s=ApprovalService()
        self.server=create_server(self.s,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'
        with urlopen(self.url+'/api/config') as r: self.config=json.load(r)

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.s.close()

    def post(self,path,data,headers=None):
        h={'Content-Type':'application/json','Origin':self.url,'X-Demo-CSRF':self.config['csrf']}
        if headers: h.update(headers)
        return urlopen(Request(self.url+path,data=json.dumps(data).encode(),headers=h))

    def test_http_evaluate_execute(self):
        with self.post('/api/evaluate',{'request':BASE}) as r: item=json.load(r)
        with self.post('/api/execute',{'id':item['id'],'token':item['grant_token'],'request':BASE}) as r: receipt=json.load(r)
        self.assertTrue(receipt['receipt']['simulated'])

    def test_cross_origin_denied(self):
        with self.assertRaises(HTTPError) as e:self.post('/api/evaluate',{'request':BASE},{'Origin':'https://evil.example'})
        self.assertEqual(e.exception.code,403)

    def test_missing_csrf_denied(self):
        with self.assertRaises(HTTPError) as e:self.post('/api/evaluate',{'request':BASE},{'X-Demo-CSRF':''})
        self.assertEqual(e.exception.code,403)

    def test_host_rebinding_denied(self):
        with self.assertRaises(HTTPError) as e:urlopen(Request(self.url+'/api/state',headers={'Host':'evil.example'}))
        self.assertEqual(e.exception.code,403)

    def test_static_source_not_exposed(self):
        with self.assertRaises(HTTPError) as e:urlopen(self.url+'/../approval.py')
        self.assertEqual(e.exception.code,404)

    def test_rule_download(self):
        with urlopen(self.url+'/rules/agent-approval.json') as r: graph=json.load(r)
        self.assertEqual(len(graph['nodes']),12)

    def test_english_routes_and_chinese_switch(self):
        for path, marker in [('/en/', b'Rules govern the next AI action.'), ('/', b'href="/en/"'), ('/app.en.js', b'window.agentGateTranslate')]:
            with self.subTest(path=path):
                with urlopen(self.url+path) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn(marker, response.read())
        with urlopen(self.url+'/rules/agent-approval.en.json') as response:
            graph = json.load(response)
        self.assertEqual(len(graph['nodes']), 12)
        self.assertEqual(graph['nodes'][0]['name'], 'Action request')

    def test_invalid_body(self):
        with self.assertRaises(HTTPError) as e:self.post('/api/evaluate',{})
        self.assertEqual(e.exception.code,400)

    def test_nonboolean_approval_rejected(self):
        with self.assertRaises(HTTPError) as e:self.post('/api/review',{'approve':'false'})
        self.assertEqual(e.exception.code,400)

if __name__=='__main__':unittest.main()
