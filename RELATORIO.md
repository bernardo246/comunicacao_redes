# Relatório — Trabalho I (Comunicação e Redes)

> Documento incremental: evolui a cada checkpoint, conforme exigido na especificação.
> **Status atual: Checkpoint 3 — Inserção de erros e perdas (simulação no cliente, NACK,
> retransmissão, criptografia).**
> Checkpoint 1 — Handshake & Sockets: entregue em 09/09/2026.
> Checkpoint 2 — Protocolo sem erros: entregue em 21/10/2026.

---

## 1. Visão geral da aplicação

Aplicação cliente-servidor que implementa, **na camada de aplicação**, um transporte
confiável de dados sobre **UDP** (socket `SOCK_DGRAM`). O UDP foi escolhido de
propósito: como ele não oferece garantia de entrega, ordenação nem detecção de
corrupção, toda a confiabilidade exigida pelo enunciado (checksum, temporizador,
número de sequência, ACK/NACK, janela) precisa ser construída pelo nosso protocolo —
que é justamente o objetivo do trabalho.

Arquivos:

| Arquivo | Responsabilidade |
| :--- | :--- |
| `config.py` | Constantes de configuração (rede, tipos de pacote, limites, defaults, simulação de falhas, chave de criptografia). Sem números mágicos espalhados. |
| `protocol.py` | Regras do protocolo: montagem/parsing de pacotes, checksum, criptografia RC4, mensagens de handshake, fragmentação, pacotes de dados, fim e ACK, e o canal simulado (`simular_canal`). Não conhece socket. |
| `server.py` | Socket do servidor: handshake, uma sessão por cliente, recepção dos dados em GBN ou SR, envio de ACK e NACK, montagem e decifragem da mensagem completa. |
| `client.py` | Socket do cliente: handshake, cifragem da mensagem, envio em três modos (individual, GBN e SR) passando pelo canal simulado, recepção segura das respostas, temporizador, tratamento de NACK e retransmissão. |

A separação `protocol.py` (regras) × `client/server.py` (rede) é proposital: permite
testar o protocolo inteiro sem subir socket nenhum (grupos A e D dos testes no README).

---

## 2. Especificação do protocolo

### 2.1 Formato do pacote

Todo pacote é uma string ASCII/UTF-8 com quatro campos separados por `|`:

```
tipo|seq|checksum|payload
```

| Campo | Descrição |
| :--- | :--- |
| `tipo` | Natureza do pacote: `HS`, `HSACK` (handshake); `MSG`, `MSGFIM`, `MSGACK` (dados, CP2; ver 2.9) e `MSGNACK` (reconhecimento negativo, CP3; ver 2.12). |
| `seq` | Número de sequência. No handshake é sempre `0`; nos dados, começa em `0` a cada mensagem. |
| `checksum` | Soma dos códigos dos caracteres de `tipo\|seq\|payload` (o pacote inteiro, menos o próprio campo do checksum; ver 2.2). |
| `payload` | Conteúdo específico do tipo de pacote. Nos dados, é um trecho de até 4 caracteres da mensagem **cifrada** (ver 2.13). |

O parsing usa `split("|", 3)`: no máximo 3 divisões, garantindo que um payload que
contenha `|` não seja picado (testado em A5).

Este documento descreve a **versão 1** do protocolo (`VERSAO_PROTOCOLO = 1` no
`config.py`). O número da versão não é transmitido no cabeçalho.

### 2.2 Checksum

Algoritmo **ASCII**, implementado à mão (`protocol.calcular_checksum`), sem biblioteca
externa: soma de `ord(c)` para cada caractere. É **fixo** para toda a aplicação — não é
negociado no handshake. Trocar de algoritmo (ex.: CRC16) exigiria mudar os dois lados, e a
função já levanta `ValueError` para algoritmo desconhecido.

**O checksum cobre o pacote inteiro**, e não só o payload: `calcular_checksum_pacote` soma
a string `tipo|seq|payload`. Assim, um caractere errado no `tipo` ou no `seq` também é
detectado (antes, um `seq` 3 que chegasse como 8 passaria sem ser percebido). O campo do
checksum fica de fora da conta, porque ele só existe depois de calculado. Por isso pacotes
sem payload também têm checksum diferente de zero: `MSGACK|0|734|`, `MSGFIM|8|755|`.

Quem envia grava o valor no cabeçalho; quem recebe recalcula sobre o que chegou e compara.
Diferente → pacote corrompido. O servidor confere todo `HS` e todo dado; o cliente confere
todo `HSACK`, `MSGACK` e `MSGNACK`.

Limitação: a soma não detecta erros que preservam o total (ex.: a troca de dois caracteres
de lugar). Os detalhes e exemplos estão no README.

### 2.3 Handshake (Checkpoint 1)

Duas mensagens, iniciadas pelo cliente:

**`HS` — cliente → servidor (proposta)**

```
HS|0|<checksum>|<modo_retransmissao>,<tipo_envio>,<tamanho_max_texto>
```

**`HSACK` — servidor → cliente (confirmação)**

```
HSACK|0|<checksum>|<modo_retransmissao>,<tipo_envio>,<tamanho_max_texto>,<tamanho_janela>
```

Exemplo real capturado na execução:

```
cliente → servidor : HS|0|1161|GBN,LOTE,30
servidor → cliente : HSACK|0|1465|GBN,LOTE,30,5
```

### 2.4 Parâmetros negociados

| Parâmetro | Valores | Quem decide |
| :--- | :--- | :--- |
| `modo_retransmissao` | `GBN` (Go-Back-N) ou `SR` (Repetição Seletiva) | Proposto pelo cliente, validado pelo servidor |
| `tipo_envio` | `LOTE` ou `IND` (individual) | Proposto pelo cliente, validado pelo servidor |
| `tamanho_max_texto` | inteiro ≥ 30 (`MIN_TEXTO`), default 30 | Proposto pelo cliente, **corrigido** pelo servidor se abaixo do mínimo |
| `tamanho_janela` | 1 a 5, inicial 5 | **Só o servidor**, aparece apenas no `HSACK` |

O `tamanho_janela` não vai no `HS`: pelo enunciado, a janela é a janela de recepção do
servidor e é ele quem a determina. O cliente descobre o valor ao ler o `HSACK`.

### 2.5 Regras de decisão do servidor

1. Datagrama que não decodifica em UTF-8 → descartado, com log.
2. Pacote fora do formato de 4 campos → descartado, com log (`ValueError`/`IndexError` tratados).
3. Tipo desconhecido (nem `HS`, nem `MSG`/`MSGFIM`) → descartado, com log. É o que acontece
   quando a corrupção simulada cai no próprio campo `tipo` (ex.: `MSG` → `LSG`).
4. `HS` com checksum inválido → descartado, sem resposta (o cliente reenvia pelo temporizador).
5. `modo_retransmissao` fora de {`GBN`, `SR`} ou `tipo_envio` fora de {`LOTE`, `IND`} → handshake recusado, sem resposta (o cliente cai no temporizador).
6. `tamanho_max_texto` < 30 → **ajustado para 30** e o valor efetivo volta no `HSACK`.
7. Caso válido → responde `HSACK` com os parâmetros efetivos + `tamanho_janela = 5` e
   cria (ou recria) a sessão do cliente.
8. Dado (`MSG`/`MSGFIM`) de um cliente sem sessão (sem handshake antes) → descartado.

Em nenhuma hipótese um pacote inválido derruba o servidor: o laço principal trata as
exceções por datagrama e segue atendendo.

### 2.6 Temporizador e retransmissão (lado cliente)

O cliente espera **1 s** por resposta (`TIMEOUT_ENVIO` no `config.py`, aplicado com
`settimeout`) e reenvia o `HS` até **5 vezes**. Se as 5 tentativas
expirarem, ele informa o erro e sai com código 1. É a primeira das características de
transporte confiável exigidas pela tabela 3.1 do livro a aparecer no código.

O limite de tentativas é a constante `MAX_TENTATIVAS_ENVIO` do `config.py` (padrão `5`).
Ela define quantas vezes o cliente manda **o mesmo pacote** sem receber resposta antes de
desistir, e vale para dois momentos:

| Momento | Pacote reenviado | Resposta esperada |
| :--- | :--- | :--- |
| Handshake | `HS` | `HSACK` |
| Envio individual | o `MSG`/`MSGFIM` atual | `MSGACK` com o mesmo `seq` |
| Envio GBN | a janela inteira, a partir da base | `MSGACK` de qualquer pacote em voo (cumulativo) |
| Envio SR | só o pacote cujo timer estourou | `MSGACK` daquele pacote |

A contagem é **por pacote**: zera toda vez que um ACK chega. No GBN, quem conta é o
pacote da base; no SR, cada pacote tem a sua contagem. No envio de dados, uma
espera sem resposta acontece quando o tempo limite estoura ou quando o Windows devolve
`ConnectionResetError` (servidor fora do ar). A contagem é feita por `contar_tentativa`,
que encerra o cliente quando o limite é atingido.

**Só o timeout conta como tentativa; o NACK não** (ver 2.12). O NACK provoca um reenvio
imediato, mas, quando vários pacotes da mesma janela chegam corrompidos, o servidor repete o
NACK do mesmo seq; se cada repetição contasse, o cliente poderia desistir sem necessidade. Um `MSGACK` com `seq` diferente do esperado
(ACK repetido de um pacote anterior) é descartado e o cliente continua esperando, mas
**sem renovar o prazo** (ver 2.8). Para mudar o limite, basta trocar o valor no
`config.py`, sem mexer no `client.py`.

O tempo de espera `TIMEOUT_ENVIO` era 5 s e foi reduzido para **1 s**. Como cliente e
servidor rodam na mesma máquina, a resposta chega em milissegundos; com 5 s, cada perda
deixava o envio parado por 5 s antes de reenviar. No pior caso, o cliente desiste de um
pacote depois de `TIMEOUT_ENVIO × MAX_TENTATIVAS_ENVIO` = 1 × 5 = **5 s**. Se o servidor
estiver em outra máquina, com uma rede mais lenta, vale aumentar esse valor: um timeout
menor que o tempo de ida e volta faz o cliente retransmitir pacotes que não se perderam.
Se um ACK chegar atrasado, depois do reenvio, ele é aceito normalmente, e o ACK
duplicado que vem depois é ignorado por ter o `seq` antigo.

### 2.7 Máquina de estados (FSM) do handshake

```
CLIENTE                                  SERVIDOR
  |                                         |
  [OCIOSO]                                [ESCUTANDO]
  |-- monta HS, envia, arma timer -------->|
  |                                        |-- valida (formato, tipo, modo, tamanho)
  |                                        |     invalido -> descarta, volta a ESCUTANDO
  |<------------------ HSACK --------------|     valido   -> responde e volta a ESCUTANDO
  [CONECTADO]                              |
  |
  timeout: reenvia HS (ate 5x) -> se estourar, [FALHA]
```

### 2.8 Recepção segura no cliente

Toda resposta que o cliente espera, o `HSACK`, cada `MSGACK` e cada `MSGNACK`, passa por
uma única função, `receber_resposta(sock, tipos_esperados, seqs_esperados, espera)`. Ela é
o **temporizador** do cliente:
- `tipos_esperados` é a lista de tipos aceitos (`[HSACK]` no handshake, `[MSGACK, MSGNACK]`
  no envio dos dados);
- `seqs_esperados` é a lista dos seqs aceitos (`[0]` no handshake, `[seq]` no envio
  individual, `range(base, proximo)` no GBN, a lista de pendentes no SR);
- `espera` é o tempo máximo (padrão `TIMEOUT_ENVIO`; o SR passa o que falta para o timer
  mais antigo estourar).

Ela devolve **uma** resposta por chamada, a primeira que passar por **todas** as regras
abaixo, na ordem; as que chegarem depois ficam no buffer do socket até a próxima chamada.
Qualquer outra coisa é descartada com uma linha `Descartado: ...` e o cliente continua
esperando dentro do mesmo prazo. Os metadados de toda resposta legível são impressos antes
do teste do checksum (`Recebido do servidor: tipo=... | seq=... | checksum=... | valido=...`),
como pede o enunciado ("os metadados das confirmações devem ser apresentados pelo cliente
à medida que chegarem"):

| # | Regra | O que barra |
| :--- | :--- | :--- |
| 1 | O datagrama cabe em `TAM_RECV` | datagrama gigante (`OSError` 10040 no Windows) |
| 2 | Veio do endereço do servidor (`HOST`, `PORTA`) | pacote forjado por outro programa ou outra porta |
| 3 | Decodifica em UTF-8 e tem os 4 campos, com `seq` e `checksum` numéricos | lixo, bytes binários, pacote incompleto |
| 4 | O checksum bate com o pacote | pacote corrompido no caminho (não se confia nem no tipo nem no seq dele) |
| 5 | O tipo está entre os esperados e o `seq` está entre os esperados | ACK repetido, ACK de outro pacote, tipo trocado, NACK de pacote já confirmado |

**Prazo fixo.** O tempo de espera é calculado uma vez (`agora + espera`), e cada
`recvfrom` usa só o que sobrou. Sem isso, um servidor que mandasse pacotes errados sem
parar renovaria o timeout a cada pacote e o cliente ficaria preso para sempre (teste E7).

**Conferência do `HSACK`.** Depois de passar pelas 5 regras, o `HSACK` ainda é conferido
por `validar_hsack`:
- o modo e o tipo de envio precisam ser os que o cliente propôs;
- o tamanho máximo precisa ser ≥ `MIN_TEXTO`;
- a janela precisa estar entre `JANELA_MIN` e `JANELA_MAX` (1 a 5).

Se o `HSACK` tiver checksum certo mas campos faltando, ou se a conferência falhar, o
cliente encerra com `Erro: HSACK malformado` ou `Erro: HSACK recusado: ...` e código 1.
Ele não tenta de novo, porque o servidor mandaria a mesma resposta.

**Saídas controladas.** Todo erro fatal passa por `encerrar_com_erro`, que imprime o
motivo, fecha o socket e chama `sys.exit(1)`. O `exit()` usado antes só existe no console
interativo do Python e não deve ser usado em script.

### 2.9 Transmissão de dados (Checkpoint 2)

Depois do handshake, o cliente envia a mensagem usando estes tipos de pacote:

| Tipo | Quem manda | Formato | Para que serve |
| :--- | :--- | :--- | :--- |
| `MSG` | cliente | `MSG\|<seq>\|<checksum>\|<até 4 caracteres>` | um pedaço da mensagem (cifrada) |
| `MSGFIM` | cliente | `MSGFIM\|<seq>\|<checksum>\|` (payload vazio) | marca o fim da mensagem; é sempre o último pacote |
| `MSGACK` | servidor | `MSGACK\|<seq>\|<checksum>\|` (payload vazio) | reconhecimento positivo: o pacote `seq` chegou íntegro e foi aceito |
| `MSGNACK` | servidor | `MSGNACK\|<seq>\|<checksum>\|` (payload vazio) | reconhecimento negativo: chegou um pacote corrompido; reenviar a partir de `seq` (CP3, ver 2.12) |

(Nas tabelas, o `|` aparece como `\|` por causa da formatação do Markdown.)

Os papéis são fixos: **o cliente é sempre o remetente** (manda os dados, tem os timers e
retransmite) e **o servidor é sempre o receptor** (só responde, não tem timer e nunca manda
dados).

**Fragmentação.** A mensagem é primeiro **cifrada inteira** (ver 2.13) e depois quebrada em
pedaços de no máximo `MAX_PAYLOAD = 4` caracteres; cada pedaço vira um `MSG` com seq a
partir de `0`. No fim entra o `MSGFIM`, com o seq seguinte. Quem faz isso é
`montar_pacotes_mensagem` do `protocol.py`, usada pelos três modos de envio do cliente.
Exemplo real para `"ola servidor tudo bem com voce"` (30 caracteres → 8 `MSG` + `MSGFIM`;
o payload é texto cifrado, por isso aparecem caracteres estranhos):

```
MSG|0|1178|[\x81Ø×   MSG|1|829|2I\x11¡   MSG|2|1184|Íû\x8a=   ...   MSG|7|716|\x8f'   MSGFIM|8|755|
```

O `MSGFIM` é enviado, confirmado e retransmitido como qualquer outro pacote. Quando o
servidor tem todos os pacotes até o `MSGFIM` em ordem, junta os pedaços, decifra e imprime
a mensagem:

```
[servidor] MENSAGEM DECIFRADA de ('127.0.0.1', 56351): 'ola servidor tudo bem com voce'
```

### 2.10 Envio no cliente: individual, GBN e SR

O cliente escolhe a forma de envio a partir da `config_sessao`, o dicionário com o que o
servidor **confirmou** no `HSACK`, e não a partir dos argumentos digitados:

| `tipo_envio` | `modo_retransmissao` | Função | Comportamento |
| :--- | :--- | :--- | :--- |
| `IND` | qualquer | `enviar_individual` | um pacote por vez: só manda o próximo depois do ACK do atual |
| `LOTE` | `GBN` | `enviar_gbn` | até `tamanho_janela` pacotes em voo, ACK cumulativo, um timer só |
| `LOTE` | `SR` | `enviar_sr` | até `tamanho_janela` pacotes em voo, ACK individual, um timer por pacote |

A janela é definida pelo servidor no `HSACK` (hoje, `JANELA_INICIAL = 5`).

Nos três modos, depois de cada espera há sempre os mesmos três casos: **timeout** (nada
chegou: reenvia), **NACK** (chegou estragado: reenvia imediatamente, sem esperar o timer) e
**ACK** (chegou certo: anda).

**Individual (`enviar_individual`).** Manda o pacote `seq` e espera a resposta só dele.
Timeout → conta uma tentativa e reenvia o mesmo pacote. NACK → reenvia o mesmo pacote
imediatamente. ACK → passa para o `seq` seguinte.

**Go-Back-N (`enviar_gbn`).** O cliente guarda `base` (o primeiro pacote ainda não
confirmado) e `proximo` (o próximo ainda não enviado). A cada volta:
1. manda todos os pacotes que cabem na janela, de `proximo` até `base + janela - 1`;
2. espera o ACK ou o NACK de qualquer pacote em voo (`range(base, proximo)`);
3. ACK do seq `n`: como o ACK é cumulativo, tudo até `n` está confirmado, então
   `base = n + 1` e a janela anda;
4. NACK do seq `n`: o servidor manda no NACK o seq que ele está esperando, então tudo antes
   de `n` já chegou. O cliente faz `base = proximo = n`, e a próxima volta reenvia a janela
   a partir de `n` imediatamente;
5. timeout: `proximo = base`, e a próxima volta reenvia a janela inteira a partir da base.

**Repetição Seletiva (`enviar_sr`).** Além de `base` e `proximo`, o cliente guarda o
conjunto `confirmados` (seqs com ACK, mesmo fora de ordem), o dicionário `hora_envio` (o
timer de cada pacote) e o dicionário `tentativas` (por pacote). A cada volta:
1. manda o que cabe na janela e arma o timer de cada pacote enviado;
2. monta a lista de pendentes (enviados e sem ACK) e espera só até o timer mais antigo
   deles estourar;
3. ACK do seq `n`: marca só o `n` como confirmado. A janela só anda quando a **base** é
   confirmada, e então pula todos os já confirmados logo depois dela;
4. NACK do seq `n`: reenvia **só** o `n`, imediatamente, e reinicia o timer dele;
5. reenvia **só** os pacotes cujo timer estourou, e rearma só o timer deles.

**Exemplo com o seq 2 perdido** (`"ola servidor tudo bem com voce"`, 9 pacotes, janela 5),
tirado da execução real com `--perder 2`:

| | GBN | SR |
| :--- | :--- | :--- |
| Envio inicial | 0 a 4; cada ACK libera um novo (5, 6) | 0 a 4; cada ACK libera um novo (5, 6) |
| O servidor responde | ACK 0, ACK 1, e repete **ACK 1** para o 3, 4, 5 e 6 (fora de ordem, descartados) | ACK 0, ACK 1, ACK 3, 4, 5, 6 (guardados no buffer) |
| O cliente | descarta os ACK 1 repetidos; a janela fica parada no 2 | a janela `[2..6]` fica cheia e o 7 não sai |
| Depois do timeout (1 s) | reenvia **2, 3, 4, 5 e 6** | reenvia **só o 2**; o ACK 2 destrava a janela e saem o 7 e o `MSGFIM` |

### 2.11 Recepção no servidor

O servidor guarda uma sessão por cliente (endereço IP e porta), criada no handshake. Os
dados de quem não fez handshake são descartados. Cada pacote recebido tem os metadados
impressos (`seq`, `checksum`, se é válido e o payload), e a recepção segue o modo da
sessão:

- **GBN (`receber_gbn`):** aceita só o pacote com o seq esperado e checksum válido, e
  responde o `MSGACK` dele. Pacote corrompido é descartado e o servidor manda
  `MSGNACK <seq_esperado>`. Pacote íntegro fora de ordem (ou duplicado) é descartado e o
  servidor repete o ACK do último pacote aceito em ordem. Não há buffer.
- **SR (`receber_sr`):** pacote corrompido é descartado e o servidor manda
  `MSGNACK <base>`. Pacote dentro da janela `[base, base + janela)` recebe ACK individual e
  vai para um buffer; quando o pacote da base chega, o servidor entrega em ordem tudo o que
  estava no buffer e a janela anda. Pacote da janela anterior (duplicado, porque o ACK dele
  se perdeu) recebe o ACK de novo, sem ser guardado outra vez.

Quando todos os pacotes até o `MSGFIM` foram entregues em ordem, `finalizar_mensagem` junta
os payloads, **decifra** a mensagem (RC4) e imprime `MENSAGEM DECIFRADA`. A sessão **não é
zerada**: ela fica marcada como `concluida`. Assim, se o ACK do `MSGFIM` se perder e o
cliente reenviar o `MSGFIM`, o servidor reconhece o duplicado e manda o ACK de novo, sem
imprimir a mensagem duas vezes. Uma mensagem nova exige um handshake novo, que recria a
sessão.

### 2.12 Reconhecimento negativo — NACK (Checkpoint 3)

Para cada pacote de dados, há três desfechos possíveis, e o servidor responde de um jeito
diferente a cada um:

| O que aconteceu com o pacote | Resposta do servidor | Quando o cliente fica sabendo |
| :--- | :--- | :--- |
| Chegou íntegro | `MSGACK` | na hora |
| Chegou corrompido (checksum não bate) | `MSGNACK` | na hora |
| Se perdeu | nada (o servidor nem sabe que ele existiu) | só quando o timer estoura |

O protocolo funcionaria só com ACK e timer: o pacote corrompido seria descartado e tratado
como perdido. O NACK existe para **ganhar tempo**: o servidor *sabe* que chegou algo
estragado, então avisa e o cliente reenvia imediatamente, em vez de esperar 1 s. O timer
continua obrigatório, porque pacote perdido não gera NACK e o próprio NACK pode se perder.
Resumo: **o ACK confirma, o NACK acelera e o timer é a rede de segurança.**

**O seq do NACK vem do estado do servidor, e não do pacote corrompido**, porque o seq
pode ser justamente o campo que estragou. No GBN é o `seq_esperado` (o cliente volta para
ele de qualquer forma); no SR é a `base` (o primeiro ainda não entregue).

Comportamento no cliente:
- **IND:** reenvia o pacote atual imediatamente.
- **GBN:** volta para o seq do NACK e reenvia a janela a partir dele imediatamente.
- **SR:** reenvia só o seq do NACK imediatamente e reinicia o timer dele.

Exemplo real (`--modo GBN --corromper 2`): a corrupção trocou um dígito do checksum
(`MSG|2|1184|...` → `MSG|2|1084|...`), o servidor registrou `GBN: seq=2 descartado,
checksum invalido` e respondeu `MSGNACK|2|814|`; o cliente imprimiu `NACK do seq=2,
reenviando a partir dele imediatamente...` e a mensagem completou em 0,1 s (com o mesmo
pacote perdido, em vez de corrompido, levou 1,2 s, por causa do timer).

**Corrupção no campo `tipo`.** Se o caractere sorteado para corromper cair no tipo
(`MSG` → `LSG`), o servidor não reconhece o pacote e o descarta como "tipo não esperado",
sem NACK. A recuperação, nesse caso, é pelo timer do cliente. Mantivemos assim porque um
canal real pode corromper qualquer campo, e o protocolo trata os dois caminhos corretamente.

**NACK repetido.** Se vários pacotes da mesma janela chegarem corrompidos, o servidor
repete o NACK do mesmo seq e o cliente reenvia a cada um. Isso gera reenvios duplicados,
mas é inofensivo: o servidor reconhece os duplicados. Optamos por esse comportamento em
troca de um código de envio mais simples (ver 6.2).

### 2.13 Criptografia simétrica — RC4 (pontuação extra)

A mensagem é cifrada com **RC4**, implementado à mão em `protocol.py`
(`criptografia_simetrica`), sem biblioteca externa. É uma cifra de fluxo: a partir da chave
compartilhada (`CHAVE_CRIPTOGRAFIA` no `config.py`), os dois lados geram a mesma sequência
de bytes (*keystream*), e cada byte da mensagem é combinado com ela por XOR. Como aplicar o
XOR duas vezes com o mesmo valor devolve o original, cifrar e decifrar são a mesma operação.

```
cliente:  texto → cifrar_mensagem → fragmentar em pedaços de 4 → MSG... + MSGFIM
servidor: junta os pedaços em ordem → decifrar_mensagem → texto
```

- A mensagem é cifrada **inteira antes de fragmentar** e decifrada **depois de remontada**,
  porque o keystream é contínuo (o 5º caractere usa o 5º byte do keystream).
- Cada byte cifrado (0 a 255) vira um caractere com `chr` e volta com `ord`, então o tamanho
  não dobra (com hexadecimal, dobrava).
- O checksum é calculado sobre o pacote já cifrado. Os dois mecanismos são independentes: o
  checksum detecta alteração mas não esconde nada; o RC4 esconde o conteúdo mas não detecta
  alteração.
- O limite de 30 caracteres vale para o texto original, digitado pelo usuário.

O passo a passo do algoritmo (KSA e PRGA), os vetores de teste e as limitações (RC4 é
inseguro para uso real, a chave se repete e é fixa no código) estão no README.

### 2.14 Simulação de erros e perdas (Checkpoint 3)

O enunciado pede que o erro seja **determinístico e definido no lado cliente**, e
verificável pelo servidor. Por isso o cliente escolhe, na linha de comando, quais pacotes
falham:

```
python client.py "<mensagem>" --perder 2          # o pacote de seq 2 se perde
python client.py "<mensagem>" --corromper 1,3     # os pacotes 1 e 3 chegam corrompidos
```

Sem essas opções, o canal é limpo (o comportamento do CP2).

- Todo pacote que o cliente envia, inclusive o `HS`, passa pela função `enviar`, que chama
  `protocol.simular_canal` antes do `sendto`. O canal devolve o pacote intacto, corrompido
  (um caractere sorteado tem um bit invertido, sem nunca mexer em um `|`) ou `None`
  (perdido: o `sendto` não é chamado). Cada falha aparece no log do cliente como
  `[SIMULACAO] PERDIDO` ou `[SIMULACAO] CORROMPIDO`.
- **Cada seq falha só na 1ª tentativa**: a retransmissão passa. Assim a demonstração
  sempre mostra a falha acontecendo e o protocolo se recuperando.
- O pacote é identificado por `(tipo, seq)`, e o `HS` tem seq `0`. Por isso `--perder 0`
  derruba **o `HS` e o `MSG 0`**, uma vez cada, o que também demonstra a retransmissão do
  handshake.
- As opções só valem **para o processo do cliente**: o `main` copia `--perder` e
  `--corromper` para `config.SEQS_PERDIDOS` e `config.SEQS_CORROMPIDOS`, e o servidor, que
  importa o `config.py` separadamente, continua com o canal limpo. O `server.py` também passa
  os seus envios pelo `simular_canal`, então perdas de ACK podem ser simuladas editando o
  `config.py` do servidor, mas isso não é o que o enunciado pede como erro definido no
  cliente.

### 2.15 O que acontece em cada falha

| Falha | Como simular | O que o servidor faz | O que o cliente faz |
| :--- | :--- | :--- | :--- |
| `HS` perdido | `--perder 0` | nada (não recebeu) | timer estoura e reenvia o `HS` (até 5x) |
| `HS` corrompido | `--corromper 0` | descarta, sem resposta | timer estoura e reenvia o `HS` |
| Dado perdido, GBN | `--perder N` | descarta os seguintes (fora de ordem) e repete o ACK do último aceito | descarta os ACKs repetidos; timer estoura e reenvia a janela a partir de N |
| Dado perdido, SR | `--perder N` | confirma e guarda os seguintes no buffer | timer de N estoura e reenvia só o N |
| Dado perdido, IND | `--envio IND --perder N` | nada | timer estoura e reenvia o N |
| Dado corrompido | `--corromper N` | descarta e manda `MSGNACK` | reenvia imediatamente (GBN: a partir do seq; SR/IND: só ele) |
| Dado com o tipo corrompido | `--corromper N` (quando o sorteio cai no tipo) | descarta como "tipo não esperado", sem NACK | timer estoura e reenvia |
| `MSGFIM` perdido | `--perder <último seq>` | não finaliza ainda | timer estoura e reenvia; o servidor então finaliza |
| ACK perdido (GBN) | `SEQS_PERDIDOS` no `config.py` do servidor | — | o ACK seguinte, cumulativo, cobre o perdido |
| ACK perdido (SR) | idem | recebe o duplicado e manda o ACK de novo | timer estoura e reenvia só aquele pacote |
| ACK do `MSGFIM` perdido | idem | sessão `concluida`: reconhece o duplicado e manda o ACK de novo | timer estoura e reenvia o `MSGFIM` |
| Resposta corrompida (ACK/NACK) | `SEQS_CORROMPIDOS` no `config.py` do servidor | — | descarta (não confia em nada dela) e espera; o timer cobre |
| Servidor fora do ar | não subir o `server.py` | — | 5 tentativas de `HS` e encerra com erro (código 1) |

---

## 3. Cobertura da tabela 3.1 (transporte confiável)

| Mecanismo | Situação no Checkpoint 3 | Como demonstrar |
| :--- | :--- | :--- |
| Soma de verificação | Calculada sobre `tipo\|seq\|payload` e transmitida em todo pacote. Conferida pelo servidor (`HS` e dados) e pelo cliente (`HSACK`, `MSGACK`, `MSGNACK`); pacote com checksum errado é descartado. | `--corromper N`: servidor registra `checksum invalido` |
| Temporizador | No cliente (`TIMEOUT_ENVIO` = 1 s, `MAX_TENTATIVAS_ENVIO` = 5 timeouts por pacote): um timer no envio individual e no GBN, um timer por pacote no SR. | `--perder N`: cliente registra `Tentativa 1: sem ACK do seq=N` |
| Número de sequência | Usado nos dados: começa em `0` a cada mensagem, ordena os pacotes no servidor, identifica qual pacote cada ACK/NACK se refere e permite reconhecer duplicados. | qualquer execução; com perda, o servidor registra `fora de ordem (esperado N)` |
| Reconhecimento positivo | `HSACK` confirma o handshake; `MSGACK` confirma cada pacote de dados (cumulativo no GBN, individual no SR). | qualquer execução: `ACK do seq=N recebido` |
| Reconhecimento negativo | `MSGNACK` quando um dado chega corrompido; o cliente reenvia imediatamente, sem esperar o timer (ver 2.12). | `--corromper N`: `NACK do seq=N, reenviando ... imediatamente` |
| Janela / paralelismo | Definida pelo servidor no `HSACK` (1–5, inicial 5) e usada no envio GBN e SR: até `tamanho_janela` pacotes em voo. | `--modo GBN` / `--modo SR`: 5 pacotes enviados antes do primeiro ACK |

---

## 4. Manual de utilização

Requisito: **Python 3** (testado na 3.13 e 3.14). Nenhuma dependência externa.
No Windows o comando é `python`; no Linux/macOS, `python3`. Rode sempre de dentro da pasta
do projeto.

**Terminal 1 — servidor** (fica esperando; encerre com `Ctrl+C`):

```
python server.py
```

**Terminal 2 — cliente (parâmetros default: GBN, LOTE, 30, canal limpo):**

```
python client.py "ola servidor tudo bem com voce"
```

Sem a mensagem, o cliente só faz o handshake. `python client.py --help` lista as opções.

| Argumento | Valores | Default |
| :--- | :--- | :--- |
| `mensagem` (posicional, 1º argumento) | texto entre aspas, de 1 até `--texto` caracteres | nenhuma (só faz o handshake) |
| `--modo` | `GBN`, `SR` | `GBN` |
| `--envio` | `LOTE`, `IND` | `LOTE` |
| `--texto` | inteiro ≥ 30 | `30` |
| `--perder` | seqs separados por vírgula (ex.: `2` ou `1,3`) | nenhum (canal limpo) |
| `--corromper` | seqs separados por vírgula (ex.: `2` ou `1,3`) | nenhum (canal limpo) |

**Os três modos de envio, com canal limpo:**

```
python client.py "ola servidor tudo bem com voce" --envio IND
python client.py "ola servidor tudo bem com voce" --modo GBN
python client.py "ola servidor tudo bem com voce" --modo SR
```

**Roteiro de demonstração das falhas (CP3).** A mensagem de 30 caracteres gera 9 pacotes
(seq 0 a 7 com dados e seq 8 com o `MSGFIM`):

| Comando | O que demonstra |
| :--- | :--- |
| `python client.py "ola servidor tudo bem com voce" --modo GBN --perder 2` | perda no GBN: reenvio da janela a partir do 2 |
| `python client.py "ola servidor tudo bem com voce" --modo SR --perder 2` | perda no SR: reenvio só do 2 (comparar com o anterior) |
| `python client.py "ola servidor tudo bem com voce" --modo GBN --corromper 2` | corrupção: NACK e reenvio imediato |
| `python client.py "ola servidor tudo bem com voce" --modo SR --corromper 2` | corrupção no SR: reenvio só do 2 |
| `python client.py "ola servidor tudo bem com voce" --envio IND --corromper 1` | corrupção no envio individual |
| `python client.py "ola servidor tudo bem com voce" --modo SR --perder 0` | perda do handshake (e do `MSG 0`) |
| `python client.py "ola servidor tudo bem com voce" --modo GBN --perder 8` | perda do `MSGFIM` |
| `python client.py "ola servidor tudo bem com voce" --modo GBN --perder 1,6 --corromper 3` | falhas combinadas |

No cmd do Windows, não cole comentários com `#` depois do comando: o cmd passa o `#` como
argumento e o `argparse` recusa.

No terminal do servidor, cada envio termina com
`MENSAGEM DECIFRADA de (...): 'ola servidor tudo bem com voce'`. Vale deixar os dois
terminais lado a lado: o cliente mostra as falhas simuladas, os ACK/NACK recebidos e as
retransmissões; o servidor mostra os metadados de cada pacote, os descartes (`checksum
invalido`, `fora de ordem`) e a mensagem final.

A mensagem é validada antes de qualquer envio: vazia ou maior que `--texto` faz o
cliente encerrar com erro do `argparse`, sem mandar nada para a rede. Como o servidor
só ajusta o `tamanho_max_texto` para cima (mínimo 30), uma mensagem que cabe no valor
proposto sempre cabe no valor confirmado no `HSACK`.

Host e porta ficam em `config.py` (`HOST = "127.0.0.1"`, `PORTA = 5000`); para rodar
entre máquinas diferentes, basta trocar o `HOST` para o IP do servidor.

---

## 5. Testes

### 5.1 Cenários de erros e perdas (Checkpoint 3)

Executados com o servidor real e o cliente usando `--perder`/`--corromper`, com a mensagem
`"ola servidor tudo bem com voce"` (9 pacotes). Em **todos** os cenários o cliente terminou
com `Mensagem enviada e confirmada pelo servidor.` (código 0) e o servidor imprimiu
`MENSAGEM DECIFRADA: 'ola servidor tudo bem com voce'`.

| Cenário | Comportamento observado |
| :--- | :--- |
| GBN, SR e IND com canal limpo | janela deslizando (5 pacotes antes do 1º ACK); no IND, envio e ACK alternados |
| GBN `--perder 2` | servidor descarta 3–6 fora de ordem e repete ACK 1; timeout; cliente reenvia 2–6 (1,2 s) |
| SR `--perder 2` | servidor guarda 3–6 no buffer; timeout; cliente reenvia só o 2 (1,1 s) |
| IND `--perder 2` | timeout e reenvio do 2 |
| GBN `--corromper 2` | servidor detecta o checksum e manda `MSGNACK 2`; reenvio imediato (0,1 s) |
| SR `--corromper 2` | NACK e reenvio só do 2 — ou, quando a corrupção cai no tipo, descarte por tipo desconhecido e recuperação pelo timer |
| IND `--corromper 1` | NACK e reenvio imediato do 1 |
| GBN `--corromper 1,3` | dois `MSGNACK 1` (o seq esperado não mudou); janela reenviada a partir do 1 |
| SR `--corromper 1,3` | NACK da base (1) reenvia o 1; o 3 volta pelo timer dele |
| GBN e SR `--corromper 1,2,3,4,5` | vários NACKs do mesmo seq geram reenvios duplicados, sem erro e sem o cliente desistir |
| SR `--perder 0` | `HS` perdido e reenviado; depois `MSG 0` perdido, a janela fica parada até o reenvio dele |
| GBN `--perder 8` | `MSGFIM` perdido; timeout e reenvio; o servidor finaliza |
| GBN `--perder 1,6 --corromper 3` e SR `--perder 0,8 --corromper 4` | falhas combinadas, todas recuperadas |

### 5.2 Bateria automatizada do Checkpoint 2 (`testes.py`)

> **Atenção:** o `testes.py` foi removido do repositório no commit `dee5181` e não foi
> atualizado para o CP3 (a assinatura de `receber_resposta` e os payloads, agora cifrados,
> mudaram). A descrição abaixo registra o que ele cobria no CP2; os comandos manuais
> equivalentes estão no README. Para consultar a versão antiga:
> `git show dee5181^:testes.py`.

Os testes estão separados em cinco blocos, do mais simples para o mais completo. A ideia
é que cada bloco responda uma pergunta diferente.

### Bloco A — o protocolo sozinho

Testa só o `protocol.py`, sem socket nenhum: montar um pacote, ler ele de volta, calcular
o checksum e montar/desmontar o HS e o HSACK. Serve para garantir que o formato
`tipo|seq|checksum|payload` está correto antes de envolver rede. Inclui o caso de um
payload que contém o próprio delimitador `|`, que é onde o parsing costuma quebrar.

**Pergunta que responde:** o protocolo, no papel, está certo?

### Bloco B — o handshake e o envio pela rede

Sobe o `server.py` e o `client.py` de verdade e faz os dois conversarem via UDP. Cobre o
handshake completo, vários clientes em sequência, o cliente escolhendo os parâmetros pela
linha de comando, a validação desses parâmetros antes do envio e o comportamento quando
não há servidor no ar (as 5 retransmissões). Cobre também o envio da mensagem nos três
modos: GBN, que é o padrão (B6); individual (B10); SR (B11). Inclui uma mensagem com `|` e
acentos (B7), a recusa de mensagens vazias, longas demais ou com caracteres que não viram
UTF-8 (B8, B9), e a conferência, no log do servidor, de que ele montou a mensagem completa
nos três modos (B12).

**Pergunta que responde:** o que foi combinado no protocolo funciona pela rede?

### Bloco C — o servidor recebendo coisa errada

Manda de propósito o que não deveria chegar: tamanho de texto abaixo do mínimo, modo de
retransmissão inexistente, pacote do tipo errado, bytes que nem são texto. Verifica que o
servidor corrige o que dá para corrigir, recusa o resto e — principalmente — continua no
ar depois de tudo isso.

**Pergunta que responde:** o servidor aguenta entrada inválida sem cair?

### Bloco D — pacotes malformados

Entrega pacotes quebrados direto para o `protocol.py`, fora da rede, e registra qual
exceção cada defeito gera (campo faltando, `seq` não numérico, payload incompleto,
algoritmo de checksum inexistente). É a contraparte do bloco C: o `protocol.py` levanta a
exceção, e quem decide o que fazer com ela é o `server.py`.

**Pergunta que responde:** o que exatamente acontece quando um pacote chega quebrado?

### Bloco E — o cliente diante de um servidor que se comporta mal

É o espelho do bloco C, do lado do cliente. O `testes.py` roda o cliente dentro do
próprio processo, apontado para um **servidor falso** na porta 5001. Esse servidor faz de
propósito o que um servidor real não deveria fazer:
- perde um pacote;
- nunca confirma;
- manda ACK velho, com checksum errado ou vindo de outra porta;
- manda lixo e um datagrama de 2000 bytes;
- inunda o cliente de ACK errado;
- responde um `HSACK` com janela 9, modo trocado, checksum errado ou campos faltando.

Verifica que o cliente descarta o que é inválido, retransmite quando precisa, recusa
o handshake quando o servidor não confirma o combinado e, quando desiste, sai com
mensagem clara e código 1, nunca com traceback e nunca travado.

Os testes E13 a E19 usam o mesmo servidor falso para conferir a janela:
- GBN: manda só o que cabe na janela, volta e reenvia a partir do pacote perdido, e trata
  o ACK como cumulativo;
- SR: manda só o que cabe na janela, reenvia só o pacote perdido, não anda a janela com o
  ACK de um pacote do meio, e desiste de um pacote pelo timer individual dele.

Cada caso está descrito no [README.md](README.md).

**Pergunta que responde:** o cliente aguenta um servidor (ou uma rede) que se comporta mal?

Para rodar um teste por vez na mão, os comandos de cada um estão no [README.md](README.md).

---

## 6. Processo de construção e uso de IA

### 6.1 Estratégia de aprendizado com IA

- **No CP1**, a IA foi usada para comparar Go-Back-N e Repetição Seletiva (buffer no
  receptor, ACK cumulativo × individual, um timer × um timer por pacote, custo de
  retransmissão; a tabela está no README). O grupo escolheu o GBN como modo padrão por ser
  mais simples de gerenciar, mantendo o SR como opção do cliente.
- A IA também ajudou a modelar a FSM do handshake (seção 2.7) e a desenhar o formato do
  pacote `tipo|seq|checksum|payload`, com o `split` limitado a 3 divisões para o payload
  poder conter `|`.
- Conceitos que ficaram mais claros com a explicação da IA: ACK cumulativo × individual,
  o papel do temporizador e por que o receptor do GBN não precisa de buffer.
- **No CP3**, a IA foi usada primeiro para ler o código já escrito pelo grupo (servidor e
  protocolo) e montar um relatório do que estava pronto e do que faltava, comparando com o
  enunciado. A partir disso, o integrante responsável pelo cliente usou a IA para entender,
  antes de implementar: por que existem ACK **e** NACK (o NACK só acelera; o timer continua
  necessário para perdas), como o servidor trata uma perda que ele nem vê, como funciona o
  RC4 (XOR com keystream, por que cifrar a mensagem inteira antes de fragmentar) e por que a
  `receber_resposta` devolve uma resposta por vez (as outras ficam no buffer do socket).
- As decisões de projeto do CP3 foram tomadas pelo grupo a partir de opções apresentadas
  pela IA: simulação definida no cliente por linha de comando (`--perder`/`--corromper`),
  passando também o `HS` pelo canal (a IA recomendava deixar o `HS` de fora; o grupo
  escolheu incluí-lo para demonstrar a retransmissão do handshake).

### 6.2 Análise crítica e debugging

Casos em que a revisão do grupo encontrou problemas no código ou nas respostas da IA, e
como foram corrigidos:

1. **Servidor morria com um único pacote malformado.** Um datagrama `LIXO` fazia
   `parsear_pacote` levantar `ValueError: not enough values to unpack (expected 4, got 1)`
   e, como o laço do `main()` não tinha tratamento, o processo inteiro encerrava.
   *Correção:* tratamento por datagrama no laço principal (`ValueError`, `IndexError`,
   `UnicodeDecodeError`), descartando o pacote e continuando a escutar.
2. **`MIN_TEXTO = 30` era declarado mas nunca usado.** O servidor confirmava um
   `tamanho_max_texto = 5`, violando o mínimo exigido pelo enunciado.
   *Correção:* `validar_parametros()` no servidor corrige para 30 e devolve o valor
   efetivo no `HSACK`; o cliente avisa quando o servidor ajustou o que ele propôs.
3. **Cliente com parâmetros hardcoded.** O handshake era sempre `GBN,LOTE,30`, embora o
   enunciado peça definição dinâmica no início da comunicação.
   *Correção:* interface de linha de comando (`--modo`, `--envio`, `--texto`) com os
   defaults do `config.py` quando nada é passado.
4. **Divergência entre documentação e código.** O README afirmava que o algoritmo de
   checksum era negociado no handshake, mas ele nunca esteve no payload do `HS`.
   *Correção:* documentação alinhada ao código — o algoritmo é fixo (ASCII).
5. **Comportamento do cliente sem servidor difere por sistema operacional.** No Windows,
   enviar UDP para porta fechada gera ICMP *port unreachable* → `ConnectionResetError`,
   que o cliente **não** tratava, e o laço de retransmissão não chegava a rodar. No Linux,
   o mesmo cenário caiu em `socket.timeout` e as 5 retransmissões aconteceram normalmente.
   *Correção:* `ConnectionResetError` passou a ser tratado como "sem resposta", junto com o
   timeout, no handshake e no envio de dados (testes B4 e E12).
6. **Cliente quebrava com qualquer resposta inesperada.** Uma resposta `LIXO`, bytes que
   não são UTF-8 ou um `seq` não numérico derrubavam o cliente com `ValueError` ou
   `UnicodeDecodeError`. No Windows, um datagrama maior que 1024 bytes derrubava com
   `OSError [WinError 10040]`.
   *Correção:* `receber_resposta` descarta o datagrama e continua esperando (teste E5).
7. **Cliente aceitava qualquer coisa que parecesse um ACK.** Não conferia o checksum do
   ACK nem do `HSACK`, não conferia quem tinha mandado o pacote e aceitava um `HSACK` com
   janela fora de 1–5 ou com um modo diferente do pedido.
   *Correção:* as regras da seção 2.8 e `validar_hsack` (testes E4, E6, E8–E11).
8. **Pacotes errados prendiam o cliente para sempre.** Cada `recvfrom` reiniciava o
   timeout, então um servidor mandando ACK errado sem parar impedia o cliente de desistir.
   *Correção:* prazo fixo por espera, calculado uma vez (teste E7).
9. **Testes desatualizados em relação ao código.** O A1 rodava um auto-teste que tinha sido
   removido do `protocol.py`. O C5 esperava que o servidor ignorasse o checksum, mas o
   servidor já o conferia. No Windows, o `testes.py` quebrava ao encerrar o servidor
   (`SIGINT` não existe para outro processo) e deixava o servidor rodando na porta 5000.
   *Correção:* A1 refeito sem depender do auto-teste, C5 atualizado para esperar o
   descarte, e o servidor encerrado com `terminate()` no Windows.

Casos encontrados no Checkpoint 2:

10. **Envio individual não mandava o `MSGFIM`.** O GBN e o SR montavam os pacotes com
    `montar_pacotes_mensagem`, que já coloca o `MSGFIM` no fim. O envio individual, mais
    antigo, montava cada pacote na mão (`fragmentar_texto` + `montar_pacote_data`) e nunca
    criava o fim. O servidor recebia e confirmava todos os pedaços, mas nunca imprimia a
    mensagem completa.
    *Correção:* o envio individual passou a usar a mesma `montar_pacotes_mensagem` do
    `protocol.py` (testes B10 e B12). Lição: antes de montar algo no cliente, conferir se
    o `protocol.py` já tem uma função pronta.
11. **Função renomeada sem atualizar quem a chamava.** `enviar_mensagem` virou
    `enviar_individual`, mas o `main` e o `testes.py` continuaram chamando o nome antigo,
    o que daria `NameError` em todo envio que não fosse GBN.
    *Correção:* as duas chamadas foram atualizadas. Ao renomear, buscar o nome antigo no
    projeto inteiro.
12. **Servidor travava no meio da bateria de testes.** O `testes.py` subia o servidor com
    `stdout=PIPE` e só lia essa saída no fim. Com os testes de envio, o log do servidor
    passou do tamanho do buffer do pipe, o `print` do servidor bloqueou e ele parou de
    responder, fazendo testes falharem sem relação com o código testado.
    *Correção:* uma thread lê a saída do servidor enquanto ele roda (`iniciar_servidor` no
    `testes.py`). O log passou a incluir também o servidor reiniciado depois do B4.

Casos encontrados no Checkpoint 3:

13. **Partes prontas que não conversavam entre si.** Ao revisar o projeto, a IA apontou
    três falhas de integração: (a) o servidor decifrava a mensagem, mas o cliente não a
    cifrava, então toda mensagem terminava em `nao foi possivel decifrar` (confirmado
    rodando `decifrar_mensagem` sobre o texto puro: `'utf-8' codec can't decode byte
    0x81`); (b) o servidor mandava `MSGNACK`, mas o cliente o descartava como "não é o
    esperado", e o NACK não tinha efeito nenhum; (c) só o servidor passava pelo
    `simular_canal`, então só ACKs se perdiam, nunca dados.
    *Correção:* o cliente passou a cifrar antes de fragmentar, aceitar e tratar o NACK e
    enviar tudo pela função `enviar`, que passa pelo canal simulado. O `TYPE_NACK` foi
    movido do `server.py` para o `config.py`, para os dois lados usarem o mesmo valor.
14. **A IA propôs restringir a corrupção ao payload, e o grupo recusou.** Nos testes, uma
    corrupção caiu no campo `tipo` (`MSG` → `LSG`), e o servidor descartou o pacote sem
    NACK. A IA sugeriu mudar `_corromper_pacote` para sempre estragar o payload e garantir o
    NACK. O grupo argumentou que o objetivo é simular um canal real, que pode corromper
    qualquer campo, e que o protocolo já trata esse caso (o timer recupera).
    *Decisão:* o sorteio foi mantido e os dois caminhos de recuperação foram documentados
    (2.12 e 2.15).
15. **Código de envio gerado pela IA complexo demais para explicar.** A primeira versão do
    tratamento de NACK tinha um controle de "NACK já atendido" no GBN e no SR, contagem de
    NACK como tentativa e várias leituras repetidas do mesmo pacote. O grupo pediu uma versão
    mais limpa. *Correção:* as três funções de envio passaram a ter a mesma estrutura
    (timeout / NACK / ACK), a contagem virou a função `contar_tentativa` e o controle de NACK
    repetido saiu. *Análise do grupo:* a simplificação tem custo, NACKs repetidos geram
    reenvios duplicados, mas o servidor trata duplicados. Por isso o NACK deixou de contar
    como tentativa: com 5 pacotes corrompidos na mesma janela, os NACKs repetidos fariam o
    cliente desistir sem necessidade. O comportamento foi validado com 17 cenários (5.1).
16. **Comandos de demonstração sugeridos pela IA não funcionavam no Windows.** A IA passou
    os comandos com comentários `# ...` no fim de cada linha, que só funcionam no bash. No
    cmd, o `#` virou um argumento a mais e o `argparse` recusou
    (`unrecognized arguments: # canal limpo`). *Correção:* o roteiro do manual (seção 4) não
    tem comentários na linha de comando.

### 6.3 Prompt log

Os principais prompts e as conversas com a IA de cada etapa estão registrados nestes
documentos (os mesmos links aparecem nos badges do README):

| Documento | Link |
| :--- | :--- |
| Relatório de uso de IA (Checkpoint 1) | <https://docs.google.com/document/d/1sqhnJL_X32p5hlbgSm2kyc2LuHvbaiGpdfhAUgdukyc/edit?usp=sharing> |
| Relatório de IA — Checkpoint 2 | <https://docs.google.com/document/d/1c5e3sfxl6mpeFje5wGmIONTZkGtjTvkRjPFccinl5sM/edit?tab=t.0> |
| Relatório de IA — Checkpoint 3 | <https://docs.google.com/document/d/10pi3DICbDcXQCscRuEF-UGoaWYMpCle-ioJwbnEk7Gc/edit?usp=sharing> |
| Relatório completo do trabalho | <https://docs.google.com/document/d/1hnnY_cLi1jdoB5Ll78GuLx-pWsAtKyu_IPw3mnkegF8/edit?tab=t.0> |



## 7. Limitações conhecidas / próximos passos

| Limitação | Observação |
| :--- | :--- |
| A janela é sempre 5 | O servidor define a janela no `HSACK` e o cliente valida a faixa 1–5, mas o servidor sempre usa `JANELA_INICIAL = 5` e a janela não muda durante a sessão. |
| O NACK do SR é da `base` | O servidor não confia no seq do pacote corrompido e manda NACK da base. Se o corrompido for outro pacote, o cliente reenvia a base (inofensivo, vira duplicado) e o pacote corrompido volta pelo timer dele. |
| Corrupção no campo `tipo` não gera NACK | O servidor descarta como tipo desconhecido; a recuperação é pelo timer (2.12). Uma melhoria possível: tratar "tipo desconhecido + checksum inválido + cliente com sessão" como dado corrompido e mandar NACK. |
| NACKs repetidos geram reenvios duplicados | Escolha do grupo em troca de código mais simples (6.2, caso 15). O NACK não conta como tentativa; com um canal que corrompesse *sempre* (ex.: `PROB_CORRUPCAO = 1.0`), o cliente reenviaria indefinidamente. O simulador determinístico só corrompe na 1ª tentativa. |
| O servidor não tem timer de sessão | Se o cliente desiste no meio, a sessão incompleta fica guardada no servidor até um novo handshake do mesmo endereço. |
| Checksum por soma simples | Não detecta erros que preservam a soma (ex.: troca de dois caracteres de lugar). |
| RC4 com chave fixa | A chave está no `config.py` dos dois lados e se repete em toda mensagem (sem nonce); RC4 não é seguro para uso real. |
| Versão do protocolo | A versão é a `1` (`VERSAO_PROTOCOLO` no `config.py`), mas ela não vai no cabeçalho dos pacotes. |
| `testes.py` desatualizado | Removido no commit `dee5181`; os cenários do CP3 estão na seção 5.1. |

Resolvidos no Checkpoint 3 (estavam nesta tabela no CP2): a inserção determinística de
erros e perdas pelo cliente (2.14); o NACK de dados (2.12); o checksum passou a cobrir
`tipo`, `seq` e `payload` (2.2); a perda do ACK do `MSGFIM` (o servidor marca a sessão como
`concluida` em vez de zerá-la e reconfirma o `MSGFIM` repetido, 2.11).

Resolvidos no Checkpoint 2 (estavam nesta tabela no CP1): o cliente envia o `MSGFIM`; o
número de sequência e a janela são usados no envio GBN e SR; `LOTE` e `IND` mudam o
comportamento do envio; o checksum é conferido no destino; o cliente trata
`ConnectionResetError` e confere o `HSACK`.
