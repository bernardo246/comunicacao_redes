## documetação do uso de IA / relatorio:
<a href="https://docs.google.com/document/d/1sqhnJL_X32p5hlbgSm2kyc2LuHvbaiGpdfhAUgdukyc/edit?usp=sharing">
      <img src="https://img.shields.io/badge/Relatorio_Uso_IA-blue?style=for-the-badge&logo=google-docs&logoColor=white" />
</a>

<a href="https://docs.google.com/document/d/1hnnY_cLi1jdoB5Ll78GuLx-pWsAtKyu_IPw3mnkegF8/edit?tab=t.0">
      <img src="https://img.shields.io/badge/Relatorio_Completo_Redes-blue?style=for-the-badge&logo=google-docs&logoColor=white" />
</a>

<a href="https://docs.google.com/document/d/1c5e3sfxl6mpeFje5wGmIONTZkGtjTvkRjPFccinl5sM/edit?tab=t.0">
      <img src="https://img.shields.io/badge/Relatorio_IA_Checkpoint 2-blue?style=for-the-badge&logo=google-docs&logoColor=white" />
</a>

<a href="https://docs.google.com/document/d/10pi3DICbDcXQCscRuEF-UGoaWYMpCle-ioJwbnEk7Gc/edit?usp=sharing">
      <img src="https://img.shields.io/badge/Relatorio_IA_Checkpoint 3-blue?style=for-the-badge&logo=google-docs&logoColor=white" />
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
- tipo — O que o pacote é: `HS` e `HSACK` (handshake), `MSG` (pedaço da mensagem),
  `MSGFIM` (fim da mensagem) e `MSGACK` (confirmação de um pacote de dados).

- seq — Qual número de sequência do pacote (pra ordenar e evitar duplicatas).
  Começa em `0` a cada mensagem.

- checksum — Soma dos códigos ASCII do pacote como um todo (`tipo|seq|payload`, sem o
  próprio campo do checksum). Calculado em todo pacote e conferido pelos dois lados: pacote
  com checksum errado é descartado.

- payload — O conteúdo/dado útil (parâmetros da sessão no handshake, até 4 caracteres da
  mensagem no `MSG`, vazio no `MSGFIM` e no `MSGACK`).


# Checagem de integridade (checksum)

Implementada **à mão** na função `calcular_checksum` do [protocol.py](protocol.py), sem
biblioteca externa nem código pronto. Serve para detectar se o pacote foi alterado no caminho.
A função soma os códigos de uma string qualquer; `calcular_checksum_pacote` a aplica sobre o
**pacote inteiro**, e não só sobre o payload.

**Algoritmo `Ascii`:** soma o código ASCII de cada caractere do payload, usando só um laço e
`ord()`.

| String | Conta | Checksum |
| :--- | :--- | :--- |
| `ABC` | 65 + 66 + 67 | `198` |
| `ola,` | 111 + 108 + 97 + 44 | `360` |
| *(vazio)* | — | `0` |

**Como é usado:**

1. **Quem envia** monta a string `tipo|seq|payload`, calcula o checksum dela e grava o
   resultado no cabeçalho (`tipo|seq|checksum|payload`). Isso é feito por
   `montar_pacote_com_checksum`, usada por todos os `montar_*` do `protocol.py`: handshake,
   dados, `MSGFIM` e ACK.
2. **Quem recebe** refaz a mesma string `tipo|seq|payload` com o que chegou, recalcula o
   checksum (`calcular_checksum_pacote`) e compara com o do cabeçalho. Para os dados, o
   resultado fica em `info["checksum_valido"]` (`parsear_pacote_data`). O `server.py`
   (`checksum_confere`) e o `client.py` conferem chamando essa mesma função.
3. **Iguais:** o pacote está íntegro. **Diferentes:** o pacote foi corrompido e é
   descartado. Sem o ACK, o remetente retransmite pelo temporizador.

**Por que o pacote inteiro:** se o checksum cobrisse só o payload, um bit errado no `seq`
(o pacote 3 chegando como 8) ou no `tipo` (um `MSG` virando `MSGFIM`, que encerraria a
mensagem antes da hora) passaria sem ser detectado. Agora qualquer alteração em `tipo`,
`seq` ou `payload` muda o valor.

**O campo do checksum fica de fora da conta.** Ele só existe depois de calculado, então não
dá para somá-lo a si mesmo. Se o próprio campo for corrompido, o valor recalculado deixa de
bater com ele, e o pacote também é descartado.

Exemplo, para o pacote `MSG|0|887|ola,`: o checksum é a soma dos códigos da string
`MSG|0|ola,`, que dá `887`.

**Limitações:**

- Pacotes sem payload (`MSGFIM`, `MSGACK`) também têm checksum diferente de `0`, porque
  `tipo` e `seq` entram na soma (`MSGFIM|3|750|`).
- A soma não detecta erros que preservam o total, como a troca de ordem dos caracteres
  (`"ab"` e `"ba"` somam igual). O algoritmo é escolhido por `ALGORITMO_CHECKSUM_PADRAO` no
  `config.py`, fixo nos dois lados e não negociado no handshake. Para trocar por outro,
  basta novo ramo em `calcular_checksum`; algoritmo desconhecido levanta `ValueError`.

---

# Criptografia simétrica (RC4)

Implementada **à mão** no [protocol.py](protocol.py), sem biblioteca externa nem código
pronto. Protege o conteúdo da mensagem: quem captura os pacotes vê só texto cifrado.
É diferente do checksum, que apenas detecta corrupção e não esconde o conteúdo.

**Algoritmo:** RC4, uma cifra de fluxo. Dois lados com a **mesma chave** geram a mesma
sequência de bytes (*keystream*), e cada byte da mensagem é combinado com ela por XOR.
Como XOR duas vezes com o mesmo valor devolve o original, **cifrar e decifrar são a mesma
operação**. São duas fases:

1. **KSA:** cria a lista `S` com os números 0 a 255 e a embaralha usando a chave:
   `j = (j + S[i] + chave[i % len(chave)]) % 256`, trocando `S[i]` e `S[j]`.
2. **PRGA:** para cada byte da mensagem, avança `i` e `j`, troca `S[i]` e `S[j]` e tira o
   byte do keystream `k = S[(S[i] + S[j]) % 256]`. O byte cifrado é `byte ^ k`.

**Funções:**

| Função | O que faz |
| :--- | :--- |
| `criptografia_simetrica(chave, dados)` | RC4 puro. Recebe a chave (`str`) e os dados (`bytes`) e devolve `bytes`. Serve para cifrar e para decifrar. Levanta `ValueError` se a chave for vazia. |
| `cifrar_mensagem(chave, texto)` | `texto` → UTF-8 → RC4 → **um caractere por byte cifrado** (`chr`), devolvido como `str`. |
| `decifrar_mensagem(chave, texto_cifrado)` | cada caractere → byte (`ord`) → RC4 → UTF-8 → texto original. Levanta `ValueError` se algum caractere tiver código acima de 255. |

**Um caractere por byte (`chr`/`ord`):** o texto cifrado tem bytes quaisquer, e o pacote é
uma string. Cada byte cifrado (0 a 255) vira **um caractere** com `chr` e volta com `ord`.
O RC4 devolve um byte para cada byte de entrada, então o tamanho cifrado é igual ao original
e a quantidade de pacotes **não dobra** (antes, com hexadecimal, dobrava).

Isso funciona com o protocolo porque:

- o `|` pode aparecer no texto cifrado, mas o `parsear_pacote` separa só 3 campos, então o
  `|` dentro do payload é preservado;
- o checksum soma `ord(c)` de cada caractere, o que continua valendo;
- os caracteres de código 128 a 255 viram 2 bytes na rede em UTF-8, mas contam como 1
  caractere para o limite de 4 do payload.

**Custos:**

- O texto cifrado **não é legível** no log: aparecem caracteres estranhos e de controle
  (códigos 0 a 31 e 127 a 159 não imprimíveis).
- O limite de 4 do payload é em **caracteres**, conforme o enunciado, e é isso que o código
  conta. Um caractere de código acima de 127 ocupa 2 bytes na rede em UTF-8, mas continua
  valendo 1 para esse limite.
- Acento no texto original (`é` tem 2 bytes em UTF-8) gera mais caracteres cifrados do que o
  texto tinha. Com texto sem acento o tamanho é exato.

**Exemplos** (as duas primeiras linhas são vetores de teste conhecidos do RC4):

| Chave | Texto | Códigos dos caracteres cifrados |
| :--- | :--- | :--- |
| `Key` | `Plaintext` | `187 243 22 232 217 64 175 10 211` (em hex: `bbf316e8d940af0ad3`) |
| `Wiki` | `pedia` | `16 33 191 4 32` (em hex: `1021bf0420`) |
| `segredo` | `ola, mundo` | 10 caracteres (mesmo tamanho do texto) |

Os códigos em hexadecimal são os vetores de teste publicados do RC4, úteis para conferir a
implementação.

**Onde entra no fluxo** (a ligação com `client.py` e `server.py` ainda não está feita):

```
cliente:  texto → cifrar_mensagem → fragmentar em pedaços de 4 → MSG... + MSGFIM
servidor: junta os pedaços → decifrar_mensagem → texto
```

A mensagem é cifrada **inteira antes de fragmentar**, e decifrada **depois de remontada**,
porque o RC4 precisa do fluxo completo e cada pacote leva só 4 caracteres. O checksum
continua sendo calculado sobre o pacote (`tipo|seq|payload`), cujo payload agora é um trecho do
texto cifrado.

**Erros tratados em `decifrar_mensagem`:** `ValueError` para caractere com código acima de
255 (não pode ter saído de `cifrar_mensagem`) e para resultado que não seja UTF-8 (o que
costuma indicar chave errada, mas não é garantido: uma chave errada pode, por acaso, gerar
UTF-8 válido).

**Limitações:**

- **RC4 é considerado inseguro** para uso real (o início do keystream tem viés estatístico e
  há ataques conhecidos). Aqui serve para demonstrar uma cifra simétrica implementada à mão.
- **Reuso de chave:** com a mesma chave em duas mensagens, o keystream se repete, e
  combinar as duas mensagens cifradas revela informação sobre os textos. Não há nonce nem
  vetor de inicialização.
- **Sem autenticação:** a cifra não detecta alteração. Quem detecta é o checksum, que é uma
  soma simples e não resiste a um atacante.
- **Troca de chave:** a chave precisa ser a mesma nos dois lados e este trabalho não resolve
  como compartilhá-la. Mandá-la no handshake a exporia em texto puro.

---

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
- Os grupos **A**, **D** e **E** não precisam de servidor. Os grupos **B** e **C** precisam de
  **dois terminais abertos**: um rodando o servidor, outro rodando o comando.

### O que cada bloco testa

Os testes estão divididos em cinco blocos, do mais simples para o mais completo:

| Bloco | O que testa | Precisa de servidor? |
| :--- | :--- | :--- |
| **A** | O protocolo sozinho: montar e ler pacote, checksum, HS e HSACK. Só chama as funções do `protocol.py`, sem socket nenhum. | Não |
| **B** | O handshake e o envio da mensagem acontecendo de verdade pela rede, entre `client.py` e `server.py` via UDP, nos três modos de envio (individual, GBN e SR). É o caminho feliz dos checkpoints 1 e 2. | Sim |
| **C** | O servidor recebendo coisa errada: parâmetro fora do permitido, tipo inesperado, pacote lixo. Mostra que ele valida e não cai. | Sim |
| **D** | Pacotes malformados entregues direto ao `protocol.py`. Documenta qual exceção cada defeito gera, sem rede no meio. | Não |
| **E** | O cliente contra um **servidor falso** que se comporta mal de propósito: perde pacote, manda lixo, mente no `HSACK`, inunda de ACK errado. Mostra que o cliente não cai nem trava, e que o GBN e o SR reenviam o que devem quando um pacote se perde. | Não (o servidor falso sobe sozinho na porta 5001) |

Resumindo: **A** prova que o protocolo está certo, **B** prova que ele funciona pela
rede, **C** prova que o servidor aguenta entrada errada, **D** mostra o que acontece
quando um pacote chega quebrado e **E** prova que o cliente aguenta um servidor que se
comporta mal.

### Rodando tudo de uma vez: `testes.py`

O `testes.py` executa a bateria inteira, sobe e derruba o servidor sozinho, compara cada
resultado com o esperado e imprime `[OK]` / `[FALHOU]` no fim, junto do log do servidor.

```bash
python3 testes.py                 # todos os testes (menos o B4, que e lento)
python3 testes.py --completo      # inclui o B4 (~5s a mais)
python3 testes.py A               # so o grupo A
python3 testes.py C1 C4           # so os testes escolhidos
python3 testes.py --silencioso    # so o veredito de cada teste, sem a saida
```

Se ja houver um servidor rodando na porta 5000, o script detecta e usa esse — nesse caso
o B4 e o B12 são pulados: o B4 precisa que ninguém esteja escutando, e o B12 precisa ler o
log do servidor, que só está disponível quando é o próprio script que o sobe.

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

**A1 — HS e HSACK montados e lidos de volta**
*Verifica:* que HS e HSACK são montados e desmontados sem perder nada.

```powershell
python -c "import protocol; p=protocol.montar_handshake_request('GBN','LOTE',50); r=protocol.montar_handshake_ack('GBN','LOTE',50,5); print(p); print(protocol.parsear_handshake(p)); print(r); print(protocol.parsear_handshake(r))"
```

Esperado: os pacotes `HS|0|1163|GBN,LOTE,50` e `HSACK|0|1467|GBN,LOTE,50,5`, cada um
seguido do dicionário com os campos separados.

> Antes este teste era `python protocol.py`, que rodava um auto-teste embutido. Esse
> bloco foi removido do `protocol.py` (commit `1515879`), então a conferência passou para
> o próprio comando acima e para o `testes.py`.

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
HS|0|1161|GBN,LOTE,30
{'tipo': 'HS', 'modo_retransmissao': 'GBN', 'tipo_envio': 'LOTE', 'tamanho_max_texto': 30}
```

**A7 — Handshake de resposta (HSACK) com outros parâmetros**
*Verifica:* o HSACK tem um campo a mais (`tamanho_janela`) e aceita SR/individual.

```powershell
python -c "import protocol,config; p=protocol.montar_handshake_ack(config.SR,config.MODO_INDIVIDUAL,50,3); print(p); print(protocol.parsear_handshake(p))"
```

Esperado:
```
HSACK|0|1326|SR,IND,50,3
{'tipo': 'HSACK', 'modo_retransmissao': 'SR', 'tipo_envio': 'IND', 'tamanho_max_texto': 50, 'tamanho_janela': 3}
```

---

### Grupo B — Handshake e envio pela rede (2 terminais)

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

Esperado: `Handshake proposto ao servidor: HS|0|1033|SR,IND,77` seguido do HSACK com
`'modo_retransmissao': 'SR'`, `'tipo_envio': 'IND'`, `'tamanho_max_texto': 77`.

**B5 — Parâmetros inválidos na linha de comando**
*Verifica:* o cliente barra antes de mandar qualquer coisa na rede.

```powershell
python client.py --texto 5
python client.py --modo XPTO
```

Esperado: `client.py: error: --texto deve ser no minimo 30 (recebido 5)` e, no segundo,
o erro de `choices` do argparse. Nenhum datagrama chega ao servidor.

**B6 — Mensagem enviada com janela GBN (o padrão)**
*Verifica:* a mensagem é quebrada em pedaços de até 4 caracteres, ganha um `MSGFIM` no
fim, e os pacotes saem de uma vez, até o tamanho da janela.

```powershell
python client.py "ola servidor"
```

Esperado: os 4 pacotes (`MSG|0|875|ola `, `MSG|1|976|serv`, `MSG|2|959|idor`,
`MSGFIM|3|750|`) enviados **antes** do primeiro ACK, depois `ACK do seq=0` a `ACK do seq=3`.
No Terminal 1, uma linha `DADOS ... valido=True` para cada pacote e, no fim,
`MENSAGEM COMPLETA ... (3 pacotes, 12 caracteres): 'ola servidor'`.

**B7 — Mensagem com `|` e acento**
*Verifica:* o delimitador do pacote e caracteres de 2 bytes em UTF-8 chegam intactos.

```powershell
python client.py "a|b é ç"
```

Esperado: `ACK do seq=0 recebido` e `ACK do seq=1 recebido`. No Terminal 1, os payloads
`'a|b '` e `'é ç'`, ambos com `valido=True`.

**B8 — Mensagem inválida na linha de comando**
*Verifica:* o cliente barra a mensagem antes de mandar qualquer coisa na rede.

```powershell
python client.py ""
python client.py "1234567890123456789012345678901"
```

Esperado: `client.py: error: a mensagem nao pode ser vazia` e
`client.py: error: a mensagem tem 31 caracteres, acima do limite de 30 (use --texto para aumentar)`.

**B9 — Mensagem com caractere que não vira UTF-8**
*Verifica:* um caractere inválido vindo do terminal (no Windows, um *surrogate* como
`\udcff`) é barrado com erro claro, em vez de quebrar no `encode` na hora do envio. Esse
caso é difícil de digitar no terminal, então só roda pelo `testes.py B9`.

**B10 — Envio individual**
*Verifica:* com `--envio IND`, cada pacote só sai depois que o anterior foi confirmado,
e o `MSGFIM` também vai no fim.

```powershell
python client.py "ola servidor" --envio IND
```

Esperado: `Pacote enviado` e `ACK do seq=N recebido` **alternando**, terminando em
`Pacote enviado: MSGFIM|3|750|` e `ACK do seq=3 recebido`. No Terminal 1,
`MENSAGEM COMPLETA ... 'ola servidor'`.

**B11 — Envio com janela SR**
*Verifica:* o envio com Repetição Seletiva funciona com o servidor real (8 pedaços +
`MSGFIM`, janela 5).

```powershell
python client.py "redes de computadores e legal!" --modo SR
```

Esperado: os 5 primeiros pacotes saem antes do primeiro ACK, e no fim aparece
`ACK do seq=8 recebido`, sem nenhuma linha `Erro`. No Terminal 1, linhas
`SR: janela agora [...]` mostrando a janela andar e
`MENSAGEM COMPLETA ... 'redes de computadores e legal!'`.

**B12 — Servidor monta a mensagem nos 3 modos**
*Verifica:* olhando o log do servidor, que ele juntou os pedaços e imprimiu
`MENSAGEM COMPLETA` para uma mensagem enviada em cada modo (individual, GBN e SR). Só roda
pelo `testes.py B12`, e é pulado se já houver um servidor no ar, porque o script precisa
ser quem sobe o servidor para ler o log dele.

Na mão, é o mesmo que rodar os três comandos abaixo e conferir no Terminal 1 que
aparecem três linhas `MENSAGEM COMPLETA`:

```powershell
python client.py "teste individual" --envio IND
python client.py "teste go-back-n" --modo GBN
python client.py "teste repeticao seletiva" --modo SR
```

**B4 — Cliente SEM servidor rodando**
*Verifica:* o que acontece quando ninguém responde. **Feche o Terminal 1 antes** (`Ctrl+C`).

```powershell
python client.py
```

Esperado (Windows e Linux): as 5 tentativas (`Tentativa 1..5: sem resposta valida do
servidor`) e depois `Erro: número máximo de tentativas de handshake excedido.`, sem
traceback.

> Detalhe importante: ao mandar UDP para uma porta fechada no próprio computador, o
> Windows devolve um ICMP *port unreachable*, que vira `ConnectionResetError` — e **não**
> `socket.timeout`. Antes o cliente só tratava o timeout e quebrava na primeira
> tentativa. Agora os dois casos são tratados como "sem resposta"; no Windows as
> tentativas acontecem quase na hora (o erro chega na hora), no Linux cada uma espera
> o `TIMEOUT_ENVIO`.

---

### Grupo C — Validação e robustez do servidor

Com o `python server.py` rodando no Terminal 1. O servidor imprime no Terminal 1 o que
recebeu, o que respondeu e o motivo de cada descarte.

**C1 — Tamanho abaixo do mínimo é corrigido pelo servidor**
*Verifica:* `MIN_TEXTO = 30` é aplicado. O cliente propõe 5, o servidor confirma 30.

```powershell
python -c "import socket,protocol,config; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(3); s.sendto(protocol.montar_handshake_request('GBN','LOTE',5).encode(),(config.HOST,config.PORTA)); print(s.recvfrom(1024)[0].decode())"
```

Esperado: `HSACK|0|1465|GBN,LOTE,30,5` e, no Terminal 1,
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

**C5 — HS com checksum errado é descartado**
*Verifica:* o servidor recalcula o checksum e descarta o `HS` cujo checksum (`1`) não
bate com o payload.

```powershell
python -c "import socket,protocol,config; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(3); s.sendto(protocol.montar_pacote('HS',0,1,'GBN,LOTE,30').encode(),(config.HOST,config.PORTA)); print(s.recvfrom(1024)[0].decode())"
```

Esperado: `TimeoutError` no Terminal 2 e `HS de ... com checksum invalido, descartado` no
Terminal 1. (No checkpoint 1 o checksum não era conferido e este pacote recebia `HSACK`.)

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

### Grupo E — Robustez do cliente (servidor falso)

Estes testes só rodam pelo `testes.py` (`python testes.py E`). O cliente roda dentro do
próprio script, apontado para um **servidor falso** na porta `5001` que responde o que o
teste mandar. Não precisa do `server.py` no ar. Para deixar os testes de desistência
rápidos, alguns usam 2 tentativas em vez de 5.

| Teste | O servidor falso... | O cliente deve... |
| :--- | :--- | :--- |
| **E1** | some com a 1ª cópia do `seq=1` | reenviar o `seq=1` uma vez e terminar a mensagem |
| **E2** | nunca confirma dados | desistir depois das tentativas e sair com código 1 |
| **E3** | manda o ACK do pacote anterior antes do certo | ignorar o ACK velho, sem retransmitir |
| **E4** | manda um `MSGACK` com checksum errado | descartar o ACK e reenviar o pacote |
| **E5** | manda `LIXO`, bytes não-UTF-8, `seq` não numérico e um datagrama de 2000 bytes | descartar os quatro e seguir |
| **E6** | deixa outro socket (outra porta) mandar o ACK | descartar o ACK de quem não é o servidor |
| **E7** | manda ACK errado a cada 50 ms, sem parar | desistir no prazo, sem ficar preso esperando |
| **E8** | responde `HSACK` com janela 9 | recusar o handshake (janela fora de 1 a 5) |
| **E9** | responde `SR` quando o cliente pediu `GBN` | recusar o handshake |
| **E10** | responde `HSACK` com checksum errado | descartar e reenviar o `HS` |
| **E11** | responde `HSACK` com checksum certo, mas sem os campos de tamanho e janela | encerrar com `HSACK malformado`, sem traceback |
| **E12** | não existe (ninguém na porta) | esgotar as tentativas e sair sem traceback |

Os testes de E1 a E12 usam o envio individual. Os de E13 a E19 testam o envio com janela:

| Teste | O servidor falso... | O cliente deve... |
| :--- | :--- | :--- |
| **E13** (GBN) | define janela 3 e nunca confirma dados | mandar só os seqs 0, 1 e 2, nem um a mais |
| **E14** (GBN) | age como receptor GBN e perde a 1ª cópia do seq 1 | voltar para o seq 1 e reenviar a partir dele (seqs recebidos: 0, 1, 2, 1, 2) |
| **E15** (GBN) | confirma só o último pacote (ACK do seq 3, o `MSGFIM`) | tratar como ACK cumulativo de 0 a 3, sem retransmitir |
| **E16** (SR) | define janela 3 e nunca confirma dados | mandar só os seqs 0, 1 e 2 |
| **E17** (SR) | confirma cada pacote e perde a 1ª cópia do seq 1 | reenviar **só** o seq 1 (seqs recebidos: 0, 1, 2, 1) |
| **E18** (SR) | janela 2: perde o seq 0 e confirma o 1 | não andar a janela com o ACK do 1; quando o 0 for confirmado, pular o 1 e liberar o 2 |
| **E19** (SR) | nunca confirma o seq 1, mas confirma os outros | reenviar só o 1 (timer individual) e desistir dele com código 1 |

---

### Resumo do que os testes cobrem

O grupo **A** cobre a montagem e leitura dos pacotes e o cálculo do checksum; o **B**
cobre o handshake completo entre `client.py` e `server.py` via UDP, incluindo a escolha
de parâmetros pela linha de comando, vários clientes em sequência, o envio de uma
mensagem nos três modos (individual, GBN e SR) com o servidor montando a mensagem
completa, e o comportamento sem servidor no ar; o **C** cobre a validação dos parâmetros
e a robustez do servidor diante de pacotes inválidos, inclusive checksum errado; o **D**
documenta o que cada pacote malformado provoca em `protocol.py`, fora da rede; o **E**
cobre a robustez do cliente diante de um servidor que perde pacotes, manda lixo ou mente
no handshake, e a retransmissão do GBN (volta e reenvia a janela) e do SR (reenvia só o
perdido).
