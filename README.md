# Dieta com Jejum — espelho recuperado

Este repositório contém o espelho estático recuperado do funil de `planocompleto.com`, mais os utilitários em `recovery-tools/`.

## Executar localmente

Com Python 3 instalado, na pasta deste repositório execute:

```powershell
py -3 recovery-tools/serve.py --root . --host 127.0.0.1 --port 8000
```

Abra `http://127.0.0.1:8000/`. O servidor fornece fallback de SPA para as rotas internas.

Auditoria dos recursos:

```powershell
py -3 recovery-tools/audit_assets.py --site .
```

## Estado da recuperação

- 37 nós e 66 ligações identificados na configuração do funil.
- 89 imagens XQuiz e 42 ficheiros de fonte incluídos.
- Auditoria anterior à publicação: 146 referências heurísticas, todas presentes.
- Os quatro ramos de idade foram percorridos localmente até à etapa de altura.
- O fluxo de cálculo ao vivo parou em 98%; o ecrã de compra não foi alcançado.
- O payload não publica o valor do campo `apiToken`; reveja e rode credenciais antes de reconfigurar integrações.
- Meta Pixel `1232754038578561` e UTMify `6a190bdb83d399e22dafdd47` aparecem na configuração. Valide as integrações antes de usar em produção.
- A configuração contém quatro destinos Cakto, mas checkout e pós-compra não foram verificados. Não foram encontrados dados legais da entidade nem links de termos/privacidade no conteúdo consultado.

## Publicação

Os ficheiros estão na branch `main`, na raiz do repositório. Isto guarda e versiona o espelho no GitHub; não ativa automaticamente o GitHub Pages. O bundle usa caminhos absolutos na raiz do domínio, por isso a publicação no endereço de projeto `/<repo>/` requer ajuste de base path ou domínio próprio e configuração do fallback SPA. Backend XQuiz, tracking e checkout Cakto continuam externos.
