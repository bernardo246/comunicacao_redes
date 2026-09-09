## documetação do uso de IA / relatorio:
<a href="https://docs.google.com/document/d/1sqhnJL_X32p5hlbgSm2kyc2LuHvbaiGpdfhAUgdukyc/edit?usp=sharing">
      <img src="https://img.shields.io/badge/Relatorio_Uso_IA-blue?style=for-the-badge&logo=google-docs&logoColor=white" />
</a>

<a href="https://docs.google.com/document/d/1hnnY_cLi1jdoB5Ll78GuLx-pWsAtKyu_IPw3mnkegF8/edit?tab=t.0">
      <img src="https://img.shields.io/badge/Relatorio_Completo_Redes-blue?style=for-the-badge&logo=google-docs&logoColor=white" />
</a>

- Relatório completo do trabalho: badge acima (Google Docs).
- Versão versionada no repositório: [RELATORIO.md](RELATORIO.md) — especificação do
  protocolo, manual de utilização, descrição dos testes e a seção "Processo de construção
  e uso de IA".



## etapa 1

## definição do modelo de comportamento de trasmissão e recepção de pacotes e seu gerenciamento

-vamos usar o GBN por questão de gerenciamente 

| Aspecto | Go-Back-N (GBN) | Repetição Seletiva (SR) |
| :--- | :--- | :--- |
| **Buffer no Receptor** | **Não exige** (descarta pacotes fora de ordem)[cite: 1]. | **Exige** (armazena pacotes fora de ordem temporariamente). |
| **Confirmação (ACK)** | **Cumulativa** (confirma "até o pacote X"). | **Individual** (confirma "o pacote X especificamente"). |
| **Temporizadores (*Timers*)** | **1 único temporizador** para o pacote mais antigo não confirmado[cite: 1]. | **1 temporizador individual** para cada pacote enviado na janela. |
| **Retransmissão** | Retransmite o pacote perdido **e todos os subsequentes** da janela. | Retransmite **apenas o pacote específico** que falhou ou expirou. |
| **Complexidade** | Mais simples de implementar no código. | Mais complexo (exige gestão de múltiplos timers e alocação de buffer). |
| **Uso da Banda** | Menos eficiente em canais com alta taxa de perdas (desperdício de tráfego). | Mais eficiente em canais com perdas (envia apenas o que é estritamente necessário). |

# variaveis para pacote
- tipo — O que o pacote é (HS, HSACK, DATA, ACK, NACK).

- seq — Qual número de sequência do pacote (pra ordenar e evitar duplicatas).

- checksum — Valor que detecta corrupção (placeholder no checkpoint 1, real no checkpoint 3).

- payload — O conteúdo/dado útil (parâmetros da sessão no handshake, dados reais no checkpoint 2).


# Variáveis de configuração (Handshake)

- **modo** — Modo de operação: envio individual/lote + confirmação GBN/SR.
  Vão no payload como **dois campos separados**: `GBN|SR` e `LOTE|IND`.
  Default: `GBN` + `LOTE` — propostos pelo cliente (`HS`), validados e confirmados pelo servidor (`HSACK`).

- **algoritmo** — Algoritmo de checksum usado nos pacotes da sessão.
  Valor: `"Ascii"` (soma dos valores ASCII dos caracteres do payload, via `ord()`).
  **Não é negociado no handshake**: é fixo nos dois lados (`ALGORITMO_CHECKSUM_PADRAO` no
  `config.py`) e por isso não aparece no payload do `HS`/`HSACK`.

- **tamanho_max_texto** — Limite total de caracteres que o cliente pode enviar na sessão.
  Mínimo: `30` (`MIN_TEXTO`) | Default: `30` (`MAX_TEXTO_DEFAULT`) — proposto pelo cliente, validado pelo servidor.

- **tamanho_janela** — Nº de pacotes em voo simultaneamente (sem confirmação).
  Faixa: `1` a `5` | Inicial: `5` — definido **só pelo servidor**, aparece apenas no `HSACK`.

---

## Como testar

Não precisa instalar nada além do Python 3 — todos os testes abaixo são comandos
avulsos que rodam direto no terminal e mostram o resultado na hora.

- Rode sempre **de dentro da pasta do projeto** (onde estão `protocol.py`, `client.py` etc.).
- Os comandos funcionam igual no **PowerShell**, no **Git Bash** e no Linux.
- Os grupos **A** e **D** não precisam de servidor. Os grupos **B** e **C** precisam de
  **dois terminais abertos**: um rodando o servidor, outro rodando o comando.

### O que cada bloco testa

Os testes estão divididos em quatro blocos, do mais simples para o mais completo:

| Bloco | O que testa | Precisa de servidor? |
| :--- | :--- | :--- |
| **A** | O protocolo sozinho: montar e ler pacote, checksum, HS e HSACK. Só chama as funções do `protocol.py`, sem socket nenhum. | Não |
| **B** | O handshake acontecendo de verdade pela rede, entre `client.py` e `server.py` via UDP. É o caminho feliz do checkpoint 1. | Sim |
| **C** | O servidor recebendo coisa errada: parâmetro fora do permitido, tipo inesperado, pacote lixo. Mostra que ele valida e não cai. | Sim |
| **D** | Pacotes malformados entregues direto ao `protocol.py`. Documenta qual exceção cada defeito gera, sem rede no meio. | Não |

Resumindo: **A** prova que o protocolo está certo, **B** prova que ele funciona pela
rede, **C** prova que o servidor aguenta entrada errada e **D** mostra o que acontece
quando um pacote chega quebrado.

### Rodando tudo de uma vez: `testes.py`

O `testes.py` executa a bateria inteira, sobe e derruba o servidor sozinho, compara cada
resultado com o esperado e imprime `[OK]` / `[FALHOU]` no fim, junto do log do servidor.

```bash
python3 testes.py                 # todos os testes (menos o B4, que e lento)
python3 testes.py --completo      # inclui o B4 (~25s a mais)
python3 testes.py A               # so o grupo A
python3 testes.py C1 C4           # so os testes escolhidos
python3 testes.py --silencioso    # so o veredito de cada teste, sem a saida
```

Se ja houver um servidor rodando na porta 5000, o script detecta e usa esse — nesse caso
o B4 é pulado, porque ele precisa que ninguém esteja escutando.

Abaixo, os mesmos testes um a um, para rodar na mão durante a apresentação.

---

Para os grupos B e C, deixe isto rodando no **Terminal 1** (ele fica parado esperando,
é o comportamento normal — encerre com `Ctrl+C`):

```powershell
python server.py
```

---

### Grupo A — Protocolo isolado (sem rede)

Testam só a montagem/leitura dos pacotes. Não envolvem socket nenhum.

**A1 — Auto-teste embutido do `protocol.py`**
*Verifica:* que HS e HSACK são montados e desmontados sem perder nada.

```powershell
python protocol.py
```

Esperado: os pacotes `HS|0|712|GBN,LOTE,50` e `HSACK|0|809|GBN,LOTE,50,5`, cada um
seguido do dicionário com os campos separados.

**A2 — Checksum com valor conhecido**
*Verifica:* a soma ASCII está correta. `A`=65, `B`=66, `C`=67 → 198.

```powershell
python -c "import protocol; print(protocol.calcular_checksum('Ascii','ABC'))"
```

Esperado: `198`

**A3 — Checksum de payload vazio**
*Verifica:* caso limite, sem caractere nenhum para somar.

```powershell
python -c "import protocol; print(protocol.calcular_checksum('Ascii',''))"
```

Esperado: `0`

**A4 — Ida e volta de um pacote (sem perda de dados)**
*Verifica:* o que foi montado é lido de volta idêntico, com `seq` e `checksum` virando inteiros.

```powershell
python -c "import protocol; p=protocol.montar_pacote('HS',7,456,'GBN,LOTE,30'); print(p); print(protocol.parsear_pacote(p))"
```

Esperado:
```
HS|7|456|GBN,LOTE,30
{'tipo': 'HS', 'seq': 7, 'checksum': 456, 'payload': 'GBN,LOTE,30'}
```

**A5 — Payload contendo o delimitador `|`**
*Verifica:* o `split("|", 3)` do `protocol.py` não pica o payload em pedaços.

```powershell
python -c "import protocol; p=protocol.montar_pacote('DATA',1,0,'texto|com|barras'); print(protocol.parsear_pacote(p)['payload'])"
```

Esperado: `texto|com|barras` (inteiro, com as barras preservadas)

**A6 — Handshake de pedido (HS)**
*Verifica:* o HS carrega modo, tipo de envio e tamanho — e **não** carrega janela.

```powershell
python -c "import protocol,config; p=protocol.montar_handshake_request(config.GBN,config.MODO_LOTE,30); print(p); print(protocol.parsear_handshake(p))"
```

Esperado:
```
HS|0|710|GBN,LOTE,30
{'tipo': 'HS', 'modo_retransmissao': 'GBN', 'tipo_envio': 'LOTE', 'tamanho_max_texto': 30}
```

**A7 — Handshake de resposta (HSACK) com outros parâmetros**
*Verifica:* o HSACK tem um campo a mais (`tamanho_janela`) e aceita SR/individual.

```powershell
python -c "import protocol,config; p=protocol.montar_handshake_ack(config.SR,config.MODO_INDIVIDUAL,50,3); print(p); print(protocol.parsear_handshake(p))"
```

Esperado:
```
HSACK|0|668|SR,IND,50,3
{'tipo': 'HSACK', 'modo_retransmissao': 'SR', 'tipo_envio': 'IND', 'tamanho_max_texto': 50, 'tamanho_janela': 3}
```

---

### Grupo B — Handshake completo pela rede (2 terminais)

Com o `python server.py` rodando no Terminal 1, use o **Terminal 2**:

**B1 — Handshake bem-sucedido**
*Verifica:* o caminho feliz completo — cliente propõe, servidor confirma, valores batem.

```powershell
python client.py
```

Esperado: duas linhas com
`{'tipo': 'HSACK', 'modo_retransmissao': 'GBN', 'tipo_envio': 'LOTE', 'tamanho_max_texto': 30, 'tamanho_janela': 5}`.
Repare que `tamanho_janela: 5` **não** foi enviado pelo cliente — quem decidiu foi o servidor.

**B2 — Vários clientes em sequência**
*Verifica:* o servidor continua no ar depois de atender e trata um cliente após o outro.

```powershell
python client.py; python client.py; python client.py
```

Esperado: o mesmo resultado do B1, três vezes seguidas.

**B3 — Servidor confirma os parâmetros que o cliente propôs**
*Verifica:* o servidor devolve exatamente o que foi pedido (aqui SR + individual + 77),
só acrescentando a janela.

```powershell
python -c "import socket,protocol,config; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(3); s.sendto(protocol.montar_handshake_request('SR','IND',77).encode(),(config.HOST,config.PORTA)); print(s.recvfrom(1024)[0].decode())"
```

Esperado: `HSACK|0|...|SR,IND,77,5`

O mesmo teste pode ser feito pelo próprio cliente, sem `python -c`:

```powershell
python client.py --modo SR --envio IND --texto 77
```

Esperado: `Handshake proposto ao servidor: HS|0|582|SR,IND,77` seguido do HSACK com
`'modo_retransmissao': 'SR'`, `'tipo_envio': 'IND'`, `'tamanho_max_texto': 77`.

**B5 — Parâmetros inválidos na linha de comando**
*Verifica:* o cliente barra antes de mandar qualquer coisa na rede.

```powershell
python client.py --texto 5
python client.py --modo XPTO
```

Esperado: `client.py: error: --texto deve ser no minimo 30 (recebido 5)` e, no segundo,
o erro de `choices` do argparse. Nenhum datagrama chega ao servidor.

**B4 — Cliente SEM servidor rodando**
*Verifica:* o que acontece quando ninguém responde. **Feche o Terminal 1 antes** (`Ctrl+C`).

```powershell
python client.py
```

Esperado **no Windows**: `ConnectionResetError: [WinError 10054]`.
Esperado **no Linux**: as 5 tentativas de retransmissão (`Tentativa 1..5: tempo limite
excedido`) e depois `Erro: número máximo de tentativas de handshake excedido.`

> Detalhe importante: ao mandar UDP para uma porta fechada no próprio computador, o
> Windows devolve um ICMP *port unreachable*, que vira `ConnectionResetError` — e **não**
> `socket.timeout`. Como o `client.py` só trata `except socket.timeout`, o laço de 5
> retransmissões **não** é acionado nesse caso: o programa quebra na primeira tentativa.
> No Linux o mesmo cenário cai em `socket.timeout` e a retransmissão acontece
> normalmente. Tratar `ConnectionResetError` junto com o timeout ficou como pendência.

---

### Grupo C — Validação e robustez do servidor

Com o `python server.py` rodando no Terminal 1. O servidor imprime no Terminal 1 o que
recebeu, o que respondeu e o motivo de cada descarte.

**C1 — Tamanho abaixo do mínimo é corrigido pelo servidor**
*Verifica:* `MIN_TEXTO = 30` é aplicado. O cliente propõe 5, o servidor confirma 30.

```powershell
python -c "import socket,protocol,config; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(3); s.sendto(protocol.montar_handshake_request('GBN','LOTE',5).encode(),(config.HOST,config.PORTA)); print(s.recvfrom(1024)[0].decode())"
```

Esperado: `HSACK|0|807|GBN,LOTE,30,5` e, no Terminal 1,
`tamanho proposto (5) abaixo do minimo, ajustando para 30`.
Pelo `client.py` o valor nem sai da máquina (ver B5).

**C2 — Modo de retransmissão desconhecido é recusado**
*Verifica:* o servidor só aceita `GBN` ou `SR` (e `LOTE` ou `IND` no tipo de envio).

```powershell
python -c "import socket,protocol,config; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(3); s.sendto(protocol.montar_handshake_request('XPTO','LOTE',30).encode(),(config.HOST,config.PORTA)); print(s.recvfrom(1024)[0].decode())"
```

Esperado: `TimeoutError` no Terminal 2 (o servidor não responde) e
`handshake recusado: modo de retransmissao invalido: XPTO, descartado` no Terminal 1.

**C3 — Pacote de tipo inesperado**
*Verifica:* um `HSACK` chegando no servidor é descartado, não confundido com pedido.

```powershell
python -c "import socket,protocol,config; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(3); s.sendto(protocol.montar_pacote('HSACK',0,0,'GBN,LOTE,30,5').encode(),(config.HOST,config.PORTA)); print(s.recvfrom(1024)[0].decode())"
```

Esperado: `TimeoutError` no Terminal 2 e `tipo nao esperado nesta etapa: HSACK, descartado`
no Terminal 1.

**C4 — Pacote lixo não derruba mais o servidor**
*Verifica:* o laço principal trata o erro por datagrama e continua atendendo.

```powershell
python -c "import socket,config; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.sendto(b'LIXO',(config.HOST,config.PORTA)); s.sendto(bytes([0xff,0xfe]),(config.HOST,config.PORTA))"
```

Esperado no Terminal 1: `pacote malformado, descartado: not enough values to unpack (expected 4, got 1)`
e `datagrama nao decodificavel, descartado: 'utf-8' codec can't decode byte 0xff...`.
Rode `python client.py` em seguida: o servidor continua respondendo normalmente.

**C5 — Checksum é enviado mas nunca conferido**
*Deveria:* detectar que o checksum (`1`) não bate com o payload. *Hoje:* responde normalmente.
Fica para o checkpoint 2/3.

```powershell
python -c "import socket,protocol,config; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(3); s.sendto(protocol.montar_pacote('HS',0,1,'GBN,LOTE,30').encode(),(config.HOST,config.PORTA)); print(s.recvfrom(1024)[0].decode())"
```

Resultado atual: `HSACK|0|807|GBN,LOTE,30,5` — o pacote corrompido passou.

---

### Grupo D — Pacotes malformados (sem rede)

Mostram o que cada tipo de defeito provoca hoje. Todos terminam em exceção crua:
nenhum deles é tratado no código.

| Teste | Comando | Erro atual |
| :--- | :--- | :--- |
| **D1** — faltam campos | `python -c "import protocol; protocol.parsear_pacote('HS\|0\|123')"` | `ValueError: not enough values to unpack (expected 4, got 3)` |
| **D2** — `seq` não numérico | `python -c "import protocol; protocol.parsear_pacote('HS\|abc\|123\|GBN,LOTE,30')"` | `ValueError: invalid literal for int() with base 10: 'abc'` |
| **D3** — HSACK sem a janela | `python -c "import protocol; protocol.parsear_handshake('HSACK\|0\|0\|GBN,LOTE,30')"` | `IndexError: list index out of range` |
| **D4** — payload incompleto | `python -c "import protocol; protocol.parsear_handshake('HS\|0\|0\|GBN')"` | `IndexError: list index out of range` |
| **D5** — algoritmo inexistente | `python -c "import protocol; protocol.calcular_checksum('CRC32','ABC')"` | `ValueError: Algoritmo de checksum não suportado` |

> Nas tabelas acima as barras aparecem escritas como `\|` por causa da formatação do
> Markdown. Ao copiar para o terminal, use a barra normal: `'HS|0|123'`.

---

### Resumo do que os testes cobrem

O grupo **A** cobre a montagem e leitura dos pacotes e o cálculo do checksum; o **B**
cobre o handshake completo entre `client.py` e `server.py` via UDP, incluindo a escolha
de parâmetros pela linha de comando, vários clientes em sequência e o comportamento sem
servidor no ar; o **C** cobre a validação dos parâmetros e a robustez do servidor diante
de pacotes inválidos (e registra a verificação de checksum como pendência do próximo
checkpoint); o **D** documenta o que cada pacote malformado provoca em `protocol.py`,
fora da rede.
