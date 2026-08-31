# Bibliotecas de terceiros servidas pelo próprio sistema

| Arquivo | Origem | Versão |
| --- | --- | --- |
| `htmx-1.9.12.min.js` | pacote npm `htmx.org`, `dist/htmx.min.js` | 1.9.12 |
| `alpine-3.14.1.min.js` | pacote npm `alpinejs`, `dist/cdn.min.js` | 3.14.1 |

Vinham da unpkg por CDN. **Toda** a interatividade do produto depende das duas — troca
de partial, modal, cronômetro, busca. Rede corporativa que bloqueie a unpkg deixava a
interface inteira inerte, sem nenhum erro visível ao usuário. Servir do próprio domínio
elimina a dependência externa e, de quebra, o terceiro que vê o tráfego.

Para atualizar: `npm pack htmx.org@<versão>` (ou baixar o dist), substituir o arquivo com
a versão no nome e trocar a referência em `web/templates/web/base.html`. O nome carrega a
versão de propósito — arquivo estático com nome novo invalida cache sozinho.
