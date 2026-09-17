"""Servidor local e banco SQLite para gestão de ordens de serviço."""
from __future__ import annotations

import json
import mimetypes
import shutil
import sqlite3
import uuid
import base64
from datetime import date
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent
DATA = ROOT / "dados"
UPLOADS = DATA / "arquivos"
DATABASE = DATA / "gestao_os.db"


def connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def setup_database():
    DATA.mkdir(exist_ok=True); UPLOADS.mkdir(exist_ok=True)
    with connection() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS empresa (id INTEGER PRIMARY KEY, nome TEXT NOT NULL, cnpj TEXT);
        CREATE TABLE IF NOT EXISTS consorcio (id INTEGER PRIMARY KEY, nome TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS consorcio_empresa (consorcio_id INTEGER, empresa_id INTEGER,
          PRIMARY KEY(consorcio_id, empresa_id), FOREIGN KEY(consorcio_id) REFERENCES consorcio(id), FOREIGN KEY(empresa_id) REFERENCES empresa(id));
        CREATE TABLE IF NOT EXISTS contrato (id INTEGER PRIMARY KEY, numero TEXT NOT NULL, objeto TEXT, consorcio_id INTEGER NOT NULL,
          FOREIGN KEY(consorcio_id) REFERENCES consorcio(id));
        CREATE TABLE IF NOT EXISTS os (id INTEGER PRIMARY KEY, numero TEXT NOT NULL UNIQUE, contrato_id INTEGER NOT NULL, local TEXT NOT NULL,
          recebida_em TEXT NOT NULL, prazo TEXT NOT NULL, empresa_id INTEGER, status TEXT NOT NULL DEFAULT 'Em andamento',
          FOREIGN KEY(contrato_id) REFERENCES contrato(id), FOREIGN KEY(empresa_id) REFERENCES empresa(id));
        CREATE TABLE IF NOT EXISTS os_item (id INTEGER PRIMARY KEY, os_id INTEGER NOT NULL, codigo TEXT NOT NULL, descricao TEXT,
          quantidade REAL NOT NULL, valor_unitario REAL NOT NULL, FOREIGN KEY(os_id) REFERENCES os(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS apontamento (id INTEGER PRIMARY KEY, os_item_id INTEGER NOT NULL, executado_em TEXT NOT NULL,
          quantidade REAL NOT NULL, observacao TEXT, FOREIGN KEY(os_item_id) REFERENCES os_item(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS anexo (id INTEGER PRIMARY KEY, os_id INTEGER NOT NULL, nome_original TEXT NOT NULL, caminho TEXT NOT NULL,
          tipo TEXT NOT NULL, enviado_em TEXT NOT NULL, FOREIGN KEY(os_id) REFERENCES os(id) ON DELETE CASCADE);
        """)
        if not db.execute("SELECT 1 FROM empresa LIMIT 1").fetchone():
            db.execute("INSERT INTO empresa (nome, cnpj) VALUES ('Via Norte Engenharia', '12.345.678/0001-90')")
            db.execute("INSERT INTO empresa (nome, cnpj) VALUES ('Sinaliza Obras Ltda.', '98.765.432/0001-10')")
            db.execute("INSERT INTO empresa (nome, cnpj) VALUES ('Pavitech Serviços', '45.678.901/0001-23')")
            db.execute("INSERT INTO consorcio (nome) VALUES ('Consórcio Mobilidade Urbana')")
            db.executemany("INSERT INTO consorcio_empresa VALUES (1, ?)", [(1,), (2,), (3,)])
            db.execute("INSERT INTO contrato (numero, objeto, consorcio_id) VALUES ('CT-042/2026', 'Manutenção e sinalização viária', 1)")
            db.execute("INSERT INTO os (numero, contrato_id, local, recebida_em, prazo, empresa_id) VALUES ('OS-2026-0187', 1, 'Av. das Nações — km 4 ao km 7', '2026-09-10', '2026-09-30', 1)")
            db.executemany("INSERT INTO os_item (os_id, codigo, descricao, quantidade, valor_unitario) VALUES (1,?,?,?,?,?)".replace('(1,?,?,?,?,?)','(1,?,?,?,?)'), [('1', 'Placa de regulamentação', 20, 185), ('6', 'Pintura de faixa', 20, 72.5), ('9', 'Tacha refletiva', 20, 28)])
            db.execute("INSERT INTO apontamento (os_item_id, executado_em, quantidade, observacao) VALUES (1, '2026-09-12', 10, 'Trecho norte concluído')")


def rows(query, args=()):
    with connection() as db: return [dict(row) for row in db.execute(query, args)]


class App(SimpleHTTPRequestHandler):
    def log_message(self, *_): pass
    def send_json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode(); self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def read_json(self): return json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or '{}')
    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/dashboard':
            return self.send_json({"cards": rows("SELECT count(*) total FROM os WHERE status='Em andamento'")[0], "orders": rows("""SELECT o.*, c.numero contrato, e.nome empresa, COALESCE(SUM(i.quantidade*i.valor_unitario),0) total
                FROM os o JOIN contrato c ON c.id=o.contrato_id LEFT JOIN empresa e ON e.id=o.empresa_id LEFT JOIN os_item i ON i.os_id=o.id GROUP BY o.id ORDER BY prazo"""), "recent": rows("""SELECT a.*, o.numero os_numero, i.codigo FROM apontamento a JOIN os_item i ON i.id=a.os_item_id JOIN os o ON o.id=i.os_id ORDER BY a.id DESC LIMIT 6""")})
        if path == '/api/form-data': return self.send_json({'empresas': rows('SELECT * FROM empresa ORDER BY nome'), 'consorcios': rows('SELECT * FROM consorcio'), 'contratos': rows('SELECT c.*, co.nome consorcio FROM contrato c JOIN consorcio co ON co.id=c.consorcio_id')})
        if path.startswith('/api/os/'):
            os_id = path.split('/')[-1]; order = rows("SELECT o.*, c.numero contrato, e.nome empresa FROM os o JOIN contrato c ON c.id=o.contrato_id LEFT JOIN empresa e ON e.id=o.empresa_id WHERE o.id=?", (os_id,))
            if not order: return self.send_json({'error':'OS não encontrada'}, 404)
            order[0]['items'] = rows("""SELECT i.*, COALESCE(SUM(a.quantidade),0) executado FROM os_item i LEFT JOIN apontamento a ON a.os_item_id=i.id WHERE i.os_id=? GROUP BY i.id""", (os_id,))
            order[0]['attachments'] = rows('SELECT * FROM anexo WHERE os_id=?', (os_id,)); return self.send_json(order[0])
        if path.startswith('/arquivos/'): return super().do_GET()
        if path == '/' or path == '/index.html':
            data=(ROOT/'index.html').read_bytes(); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.end_headers(); return self.wfile.write(data)
        return super().do_GET()
    def do_POST(self):
        path=urlparse(self.path).path; data=self.read_json()
        try:
            with connection() as db:
                if path == '/api/os':
                    cur=db.execute("INSERT INTO os (numero,contrato_id,local,recebida_em,prazo,empresa_id) VALUES (?,?,?,?,?,?)", (data['numero'],data['contrato_id'],data['local'],data['recebida_em'],data['prazo'],data.get('empresa_id') or None)); oid=cur.lastrowid
                    for item in data.get('itens',[]): db.execute("INSERT INTO os_item (os_id,codigo,descricao,quantidade,valor_unitario) VALUES (?,?,?,?,?)", (oid,item['codigo'],item.get('descricao',''),item['quantidade'],item['valor_unitario']))
                    return self.send_json({'id':oid},201)
                if path == '/api/apontamentos':
                    db.execute("INSERT INTO apontamento (os_item_id,executado_em,quantidade,observacao) VALUES (?,?,?,?)", (data['os_item_id'],data['executado_em'],data['quantidade'],data.get('observacao',''))); return self.send_json({'ok':True},201)
                if path == '/api/anexos':
                    name = Path(data['nome']).name
                    suffix = Path(name).suffix.lower()
                    if suffix not in {'.pdf', '.dwg'}: return self.send_json({'error':'Envie apenas arquivos PDF ou DWG.'}, 400)
                    stored = f"{uuid.uuid4().hex}{suffix}"
                    (UPLOADS / stored).write_bytes(base64.b64decode(data['conteudo']))
                    db.execute("INSERT INTO anexo (os_id,nome_original,caminho,tipo,enviado_em) VALUES (?,?,?,?,?)", (data['os_id'], name, stored, suffix[1:].upper(), date.today().isoformat()))
                    return self.send_json({'ok': True}, 201)
                if path.endswith('/concluir'):
                    db.execute("UPDATE os SET status='Concluída' WHERE id=?", (path.split('/')[3],)); return self.send_json({'ok':True})
                if path == '/api/empresa': db.execute('INSERT INTO empresa (nome,cnpj) VALUES (?,?)',(data['nome'],data.get('cnpj','')))
                elif path == '/api/consorcio':
                    cur=db.execute('INSERT INTO consorcio (nome) VALUES (?)',(data['nome'],)); db.executemany('INSERT INTO consorcio_empresa VALUES (?,?)',[(cur.lastrowid,x) for x in data.get('empresas',[])])
                elif path == '/api/contrato': db.execute('INSERT INTO contrato (numero,objeto,consorcio_id) VALUES (?,?,?)',(data['numero'],data.get('objeto',''),data['consorcio_id']))
                else: return self.send_json({'error':'Rota inválida'},404)
            return self.send_json({'ok':True},201)
        except (KeyError, ValueError, sqlite3.IntegrityError) as e: return self.send_json({'error':str(e)},400)


if __name__ == '__main__':
    setup_database(); print('Sistema local em http://127.0.0.1:8765'); ThreadingHTTPServer(('127.0.0.1',8765),App).serve_forever()
