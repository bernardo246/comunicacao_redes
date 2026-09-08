## documetação do uso de IA / relatorio:
<a href="https://docs.google.com/document/d/1sqhnJL_X32p5hlbgSm2kyc2LuHvbaiGpdfhAUgdukyc/edit?usp=sharing">
      <img src="https://img.shields.io/badge/Relatorio_Uso_IA-blue?style=for-the-badge&logo=google-docs&logoColor=white" />
</a>

<a href="[https://docs.google.com/document/d/1sqhnJL_X32p5hlbgSm2kyc2LuHvbaiGpdfhAUgdukyc/edit?usp=sharing](https://docs.google.com/document/d/1hnnY_cLi1jdoB5Ll78GuLx-pWsAtKyu_IPw3mnkegF8/edit?tab=t.0)">
      <img src="https://img.shields.io/badge/Relatorio_Completo_Redes-blue?style=for-the-badge&logo=google-docs&logoColor=white" />
</a>



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
  Default: `"GBN-LOTE"` — proposto pelo cliente (`HS`), confirmado pelo servidor (`HSACK`).

- **algoritmo** — Algoritmo de checksum usado nos pacotes da sessão.
  Valor: `"ASCII"` (soma dos valores ASCII dos caracteres do payload, via `ord()`) — proposto pelo cliente (`HS`), confirmado pelo servidor (`HSACK`).

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

**B4 — Cliente SEM servidor rodando**
*Verifica:* o que acontece quando ninguém responde. **Feche o Terminal 1 antes** (`Ctrl+C`).

```powershell
python client.py
```

Esperado **no Windows**: `ConnectionResetError: [WinError 10054]`.

> Detalhe importante: ao mandar UDP para uma porta fechada no próprio computador, o
> Windows devolve um ICMP *port unreachable*, que vira `ConnectionResetError` — e **não**
> `socket.timeout`. Como o `client.py` só trata `except socket.timeout`, o laço de 5
> retransmissões **não** é acionado nesse caso: o programa quebra na primeira tentativa.
> A retransmissão só entra em ação quando o pacote é descartado em silêncio (firewall,
> perda real na rede, máquina remota desligada).

---

### Grupo C — Robustez: o que ainda falta implementar

Estes comandos **não** são bugs do teste — eles demonstram limitações reais do código
atual. Com o `python server.py` rodando no Terminal 1:

**C1 — Servidor aceita tamanho abaixo do mínimo**
*Deveria:* recusar, porque `MIN_TEXTO = 30`. *Hoje:* aceita 5 numa boa.

```powershell
python -c "import socket,protocol,config; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(3); s.sendto(protocol.montar_handshake_request('GBN','LOTE',5).encode(),(config.HOST,config.PORTA)); print(s.recvfrom(1024)[0].decode())"
```

Resultado atual: `HSACK|0|761|GBN,LOTE,5,5` — o servidor confirmou o 5.

**C2 — Checksum é enviado mas nunca conferido**
*Deveria:* detectar que o checksum (`1`) não bate com o payload. *Hoje:* responde normalmente.

```powershell
python -c "import socket,protocol,config; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(3); s.sendto(protocol.montar_pacote('HS',0,1,'GBN,LOTE,30').encode(),(config.HOST,config.PORTA)); print(s.recvfrom(1024)[0].decode())"
```

Resultado atual: `HSACK|0|807|GBN,LOTE,30,5` — o pacote corrompido passou.

**C3 — Pacote de tipo desconhecido**
*Verifica:* o `else` do `server.py`. O servidor não responde nada.

```powershell
python -c "import socket,protocol,config; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(3); s.sendto(protocol.montar_pacote('HSACK',0,0,'GBN,LOTE,30,5').encode(),(config.HOST,config.PORTA)); print(s.recvfrom(1024)[0].decode())"
```

Esperado: `TimeoutError` no Terminal 2 (ninguém respondeu) e `Tipo não encontrado`
impresso no Terminal 1.

**C4 — Um pacote lixo derruba o servidor inteiro**
*Deveria:* ignorar e continuar. *Hoje:* o `server.py` morre com traceback, porque o laço
do `main()` não tem `try/except`.

```powershell
python -c "import socket,config; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.sendto(b'LIXO',(config.HOST,config.PORTA))"
```

Resultado atual: no Terminal 1 aparece
`ValueError: not enough values to unpack (expected 4, got 1)` e o servidor **encerra**.
Rode `python client.py` depois para confirmar que ele não responde mais.

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
cobre o handshake completo entre `client.py` e `server.py` via UDP, incluindo vários
clientes em sequência e o comportamento sem servidor no ar; o **C** demonstra o que
ainda falta (validação dos parâmetros no servidor, verificação do checksum e tratamento
de erro no laço principal); o **D** documenta o que cada pacote malformado provoca hoje.
