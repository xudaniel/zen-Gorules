"""Generate inspectable GoRules JDM. Run after intentionally editing policy definitions."""
import json
from pathlib import Path

# severity: 1 allow, 2 redact, 3 human review, 4 deny; first matching row wins.
CHECKS = [
 ('identity', '身份与权限', [
  ('facts.agent_active == false',4,'AGENT_DISABLED','智能体已停用',''),
  ('facts.scope_allowed == false',4,'SCOPE_DENIED','该智能体没有此工具的使用权限',''),
  ('request.action == "delete_records"',3,'DELETE_OWNER','删除操作需要业务负责人确认','owner'),
  ('true',1,'IDENTITY_OK','身份有效，操作在授权范围内','')]),
 ('data', '数据分级', [
  ('facts.classification == "secret" and facts.external',4,'SECRET_EGRESS','密钥或机密数据禁止发送到外部',''),
  ('facts.classification == "secret"',3,'SECRET_INTERNAL','内部机密访问需要安全人员批准','security'),
  ('facts.classification == "customer" and facts.external and facts.redactable',2,'PII_REDACT','外发客户数据需先脱敏',''),
  ('facts.classification == "customer" and facts.external',3,'PII_REVIEW','客户数据无法完整自动脱敏，需安全复核','security'),
  ('facts.classification == "internal" and facts.external',3,'INTERNAL_EGRESS','内部资料外发需要业务负责人批准','owner'),
  ('true',1,'DATA_OK','数据分类允许此操作','')]),
 ('destination', '目标可信度', [
  ('facts.destination == "blocked"',4,'TARGET_BLOCKED','目标命中演示禁止名单',''),
  ('facts.destination == "external" and request.action == "http_request"',3,'UNKNOWN_API','未知外部接口需要安全复核','security'),
  ('facts.destination == "external" and request.action == "send_email"',3,'NEW_RECIPIENT','新外部联系人需要业务负责人确认','owner'),
  ('facts.destination == "trusted"',1,'TRUSTED_TARGET','目标属于演示合作方名单',''),
  ('true',1,'TARGET_OK','目标检查通过','')]),
 ('environment', '运行环境', [
  ('request.environment == "production" and request.action == "delete_records"',4,'PROD_DELETE','演示政策禁止生产环境批量删除',''),
  ('request.environment == "production" and request.action == "update_record"',3,'PROD_WRITE','生产数据修改需要业务负责人批准','owner'),
  ('request.environment == "production" and request.action == "http_request"',3,'PROD_API','生产环境接口操作需要安全人员批准','security'),
  ('request.environment == "sandbox"',1,'SANDBOX','测试环境，继续应用数据与权限限制',''),
  ('true',1,'ENV_OK','运行环境检查通过','')]),
 ('refund_eligibility', '退款资格', [
  ('request.action != "issue_refund"',1,'NOT_REFUND','本次操作不是退款',''),
  ('facts.order_exists == false',4,'ORDER_NOT_FOUND','支付沙箱中找不到订单',''),
  ('request.cost <= 0',4,'REFUND_AMOUNT','退款金额必须大于零',''),
  ('request.cost > facts.refundable_amount',4,'REFUND_BALANCE','退款金额超过订单剩余可退金额',''),
  ('facts.order_age_days > 60',4,'REFUND_WINDOW','订单已超过六十天退款期限',''),
  ('request.cost > 500',4,'REFUND_CAP','单次退款超过五百美元上限',''),
  ('true',1,'REFUND_ELIGIBLE','订单与退款金额符合基本条件','')]),
 ('refund_operations', '退款运营规则', [
  ('request.action != "issue_refund"',1,'NOT_REFUND','本次操作不是退款',''),
  ('request.cost > 50',3,'REFUND_OWNER','退款超过五十美元，需要客服主管批准','support'),
  ('facts.order_age_days > 30',3,'REFUND_AGE_REVIEW','订单超过三十天，需要客服主管复核','support'),
  ('true',1,'REFUND_OPS_OK','退款在客服自动处理范围内','')]),
 ('refund_fraud', '退款风险', [
  ('request.action != "issue_refund"',1,'NOT_REFUND','本次操作不是退款',''),
  ('facts.refund_risk_flag',3,'REFUND_RISK','订单命中支付沙箱风险标记，需要安全复核','security'),
  ('facts.prior_refunds >= 2',3,'REFUND_HISTORY','客户历史退款次数较多，需要安全复核','security'),
  ('true',1,'REFUND_RISK_OK','退款历史与风险标记正常','')]),
 ('refund_finance', '退款财务规则', [
  ('request.action != "issue_refund"',1,'NOT_REFUND','本次操作不是退款',''),
  ('request.cost > 200',3,'REFUND_FINANCE','退款超过二百美元，需要财务批准','finance'),
  ('true',1,'REFUND_FINANCE_OK','退款金额无需财务复核','')]),
 ('volume', '操作规模', [
  ('request.records > 1000',4,'BULK_LIMIT','单次超过 1,000 条记录，禁止执行',''),
  ('facts.executions_hour >= 20',4,'RATE_LIMIT','近一小时已执行 20 次，达到演示频率上限',''),
  ('request.records > facts.review_record_limit',3,'BULK_REVIEW','记录数超过当前规则版本的人工复核阈值','owner'),
  ('facts.executions_hour >= 10',3,'BURST_REVIEW','近一小时操作密集，需要安全复核','security'),
  ('true',1,'VOLUME_OK','记录数与近期频率正常','')]),
 ('budget', '成本与额度', [
  ('request.action != "issue_refund" and request.cost > 500',4,'SINGLE_BUDGET','单次预计成本超过 500 演示点数',''),
  ('request.action != "issue_refund" and facts.cost_hour + request.cost > 1000',4,'TOTAL_BUDGET','近一小时累计成本将超过 1,000 演示点数',''),
  ('request.action != "issue_refund" and request.cost > 100',3,'FINANCE_REVIEW','预计成本超过 100 点，需要财务批准','finance'),
  ('request.action != "issue_refund" and request.cost > 0',1,'BUDGET_OK','预计成本在预算范围内',''),
  ('true',1,'NO_COST','本次操作不消耗演示点数','')]),
 ('content', '内容与指令', [
  ('facts.payload_bytes > 12000',4,'PAYLOAD_LIMIT','操作内容过大，超出演示允许范围',''),
  ('facts.injection_signal',3,'INSTRUCTION_REVIEW','发现越权指令关键词，需要安全人员复核','security'),
  ('facts.secret_signal',3,'SECRET_SIGNAL','发现疑似密钥标记，按机密数据复核','security'),
  ('request.action == "send_email" and facts.empty_payload',4,'EMPTY_MESSAGE','邮件内容不能为空',''),
  ('true',1,'CONTENT_OK','内容检查未发现演示规则中的异常','')]),
 ('context', '业务理由', [
  ('facts.purpose_length < 5',3,'PURPOSE_MISSING','业务理由不足五个字符，需要负责人补充确认','owner'),
  ('request.environment == "production" and request.action != "read_file" and facts.ticket_missing',3,'CHANGE_TICKET','生产变更没有关联工单，需要负责人批准','owner'),
  ('request.action == "read_file" and request.records > 50',3,'READ_SCOPE','大范围读取需要业务负责人确认','owner'),
  ('true',1,'CONTEXT_OK','业务理由与工单检查通过','')])]

def build():
    nodes=[{'id':'request','type':'inputNode','name':'操作申请','position':{'x':0,'y':200}}]
    edges=[]
    previous='request'
    for i,(key,title,rules) in enumerate(CHECKS):
        node={'id':key,'type':'decisionTableNode','name':title,'position':{'x':300*(i+1),'y':200},'content':{
         'hitPolicy':'first','passThrough':True,
         'inputs':[{'id':'condition','name':'判断条件','type':'expression','field':''}],
         'outputs':[{'id':k,'name':k,'type':'expression','field':f'checks.{key}.{k}'} for k in ['severity','code','reason','reviewer']],
         'rules':[{'_id':code,'condition':condition,'severity':str(severity),'code':json.dumps(code),'reason':json.dumps(reason,ensure_ascii=False),'reviewer':json.dumps(reviewer)} for condition,severity,code,reason,reviewer in rules]}}
        nodes.append(node);edges.append({'id':previous+'-'+key,'sourceId':previous,'targetId':key,'type':'edge'});previous=key
    final_x=300*(len(CHECKS)+1)
    nodes.append({'id':'severity','type':'expressionNode','name':'合并风险等级','position':{'x':final_x,'y':200},'content':{'passThrough':True,'expressions':[{'id':'maximum','key':'severity','value':'max(['+', '.join('checks.'+key+'.severity' for key,_,_ in CHECKS)+'])'}]}})
    edges.append({'id':previous+'-severity','sourceId':previous,'targetId':'severity','type':'edge'})
    nodes.append({'id':'verdict','type':'decisionTableNode','name':'最终决策','position':{'x':final_x+300,'y':200},'content':{'hitPolicy':'first','passThrough':True,'inputs':[{'id':'severity','name':'最高风险等级','field':'severity'}],'outputs':[{'id':'outcome','name':'决策','field':'outcome'}],'rules':[{'_id':v,'severity':str(n),'outcome':json.dumps(v)} for n,v in [(4,'deny'),(3,'review'),(2,'redact'),(1,'allow')]]}})
    nodes.append({'id':'response','type':'outputNode','name':'审批结论','position':{'x':final_x+600,'y':200}})
    edges.extend([{'id':'severity-verdict','sourceId':'severity','targetId':'verdict','type':'edge'},{'id':'verdict-response','sourceId':'verdict','targetId':'response','type':'edge'}])
    return {'contentType':'application/vnd.gorules.decision','nodes':nodes,'edges':edges}

if __name__=='__main__':
    p=Path(__file__).parent/'rules'/'agent-approval.json'
    p.write_text(json.dumps(build(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{len(CHECKS)} checks; {sum(len(x[2]) for x in CHECKS)+4} decision rows; wrote {p.name}')
