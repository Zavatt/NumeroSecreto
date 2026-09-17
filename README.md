# Gestão de Ordens de Serviço

Aplicação local para controlar contratos, consórcios, ordens de serviço (OS), itens, produção diária e os arquivos técnicos entregues ao fim do serviço. Os dados ficam em um banco SQLite no próprio computador: não há conta, nuvem nem envio de dados a terceiros.

## Como iniciar

Requer apenas Python 3.11 ou superior.

```bash
python3 app.py
```

Abra `http://127.0.0.1:8765` no navegador. Na primeira execução, o arquivo `dados/gestao_os.db` é criado automaticamente com dados de exemplo; eles podem ser removidos e substituídos pelos dados reais.

## Fluxo sugerido

1. Cadastre as empresas que formam o consórcio e depois crie o consórcio.
2. Cadastre o contrato vinculado ao consórcio.
3. Receba e crie a OS, definindo prazo, local, empresa executora e quantidades por item.
4. No controle da OS, registre diariamente as unidades executadas em cada item.
5. Ao concluir a OS, anexe os arquivos PDF e DWG do projeto e marque-a como concluída.

## Backup

Pare o sistema e copie o arquivo `dados/gestao_os.db` para um local seguro. Para restaurar, substitua esse arquivo por sua cópia de backup com o sistema fechado.
