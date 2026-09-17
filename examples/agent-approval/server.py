"""Run the local-only demo: python server.py --port 8767."""
import argparse
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from approval import ApprovalError, ApprovalService, ROOT


def create_server(service, port=8767):
    csrf=secrets.token_urlsafe(24)

    class Handler(BaseHTTPRequestHandler):
        def reply(self,status,body,kind='application/json; charset=utf-8'):
            raw=json.dumps(body,ensure_ascii=False).encode() if kind.startswith('application/json') else body
            self.send_response(status)
            self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def trusted(self):
            hosts={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
            return self.headers.get('Host') in hosts

        def do_GET(self):
            if not self.trusted():
                return self.reply(403,{'error':'HOST_REJECTED','message':'仅支持本机访问。'})
            path=urlsplit(self.path).path
            if path=='/api/config':
                return self.reply(200,dict(service.config(),csrf=csrf))
            if path=='/api/state':
                return self.reply(200,service.state())
            files={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8'),'/favicon.svg':('favicon.svg','image/svg+xml')}
            if path=='/rules/agent-approval.json':
                return self.reply(200,service.rule_content.encode(),'application/octet-stream')
            if path not in files:
                return self.reply(404,{'error':'NOT_FOUND','message':'页面不存在。'})
            name,kind=files[path]
            self.reply(200,(ROOT/'static'/name).read_bytes(),kind)

        def do_POST(self):
            origin=self.headers.get('Origin')
            allowed={f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}
            if not self.trusted() or origin not in allowed or not secrets.compare_digest(self.headers.get('X-Demo-CSRF',''),csrf):
                return self.reply(403,{'error':'ORIGIN_REJECTED','message':'请求来源无效，请从本机操作台重试。'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length<1 or length>64000:
                    raise ApprovalError('BODY_SIZE','请求大小不符合限制。',400)
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                    raise ApprovalError('CONTENT_TYPE','请使用 JSON 请求。',400)
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):
                    raise ApprovalError('INVALID_BODY','请求必须是对象。',400)
                path=urlsplit(self.path).path
                if path=='/api/evaluate':
                    result=service.evaluate(data['request'])
                elif path=='/api/review':
                    if type(data['approve']) is not bool:
                        raise ApprovalError('INVALID_BODY','审批选择必须是布尔值。',400)
                    result=service.review(data['id'],data['reviewer'],data['note'],data['approve'])
                elif path=='/api/execute':
                    result=service.execute(data['id'],data.get('token'),data['request'])
                elif path=='/api/policy':
                    result=service.switch_policy(data['version'])
                else:
                    raise ApprovalError('NOT_FOUND','接口不存在。',404)
                self.reply(200,result)
            except ApprovalError as exc:
                self.reply(exc.status,{'error':exc.code,'message':exc.message})
            except (ValueError,KeyError,TypeError):
                self.reply(400,{'error':'INVALID_BODY','message':'请求字段缺失或格式不正确。'})
            except Exception:
                import traceback
                traceback.print_exc()
                self.reply(500,{'error':'INTERNAL_ERROR','message':'处理失败，请查看服务日志。'})

        def log_message(self,format,*args):
            # Do not log submitted request bodies or grant tokens.
            print(f'[local demo] {format % args}',flush=True)

    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8767)
    parser.add_argument('--db',type=Path,default=ROOT/'.demo-data'/'approval.sqlite')
    args=parser.parse_args()
    args.db.parent.mkdir(parents=True,exist_ok=True)
    service=ApprovalService(args.db)
    args.db.chmod(0o600)
    server=create_server(service,args.port)
    print(f'AgentGate demo: http://127.0.0.1:{server.server_port} (simulated tools only)',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        service.close()
