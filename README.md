# Trendshift reader

Script em Python que lê o ranking ao vivo de [trendshift.io](https://trendshift.io) e grava os repositórios em tendência em JSON.

Não usa dependências além da biblioteca padrão. Precisa de Python 3.10 ou mais recente.

## Uso

Ranking de hoje, impresso no terminal:

```bash
python3 trendshift.py
```

Gravar em arquivo:

```bash
python3 trendshift.py -o trending.json
```

Outras janelas e um recorte da lista:

```bash
python3 trendshift.py --period weekly
python3 trendshift.py --period monthly --limit 10
python3 trendshift.py --period yearly -o yearly.json
```

| Opção | O que faz |
| --- | --- |
| `--period` | `today` (padrão), `weekly`, `monthly` ou `yearly` |
| `-o`, `--output` | Caminho do JSON. Sem isso, a saída vai para o terminal |
| `--limit` | Quantidade máxima de repositórios. `0` traz a lista inteira |
| `--timeout` | Tempo máximo da requisição, em segundos (padrão: 30) |

## O que sai no JSON

Cada execução devolve um objeto com a origem, o período, a hora da coleta e a lista ordenada. Um item tem rank, nome `owner/repo`, links do GitHub e do Trendshift, descrição, linguagem, estrelas, forks, o quanto subiu no período (`stars_gained`, `forks_gained`), score, tags e menções.

`stars_gained` é a variação da janela escolhida: o dia, a semana, o mês ou o ano. O campo `window` diz a qual intervalo aquele número se refere.

`extracted_from` indica de onde os dados saíram. `page-data` é o ranking completo publicado na página. `json-ld` é a reserva, com menos campos numéricos, usada se o formato interno da página mudar.

## Como a leitura funciona

O Trendshift é um site Next.js. O script baixa o HTML e extrai a lista que a página já envia ao navegador. Não há API separada e nenhum login.
