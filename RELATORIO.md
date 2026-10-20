# Relatório — Trabalho I (Comunicação e Redes)

> Documento incremental: evolui a cada checkpoint, conforme exigido na especificação.
> **Status atual: Checkpoint 1 — Handshake & Sockets (entrega em 09/09/2026).**

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
| `config.py` | Constantes de configuração (rede, protocolo, limites, defaults). Sem números mágicos espalhados. |
| `protocol.py` | Regras do protocolo: montagem/parsing de pacotes, checksum e mensagens de handshake. Não conhece socket. |
| `server.py` | Socket do servidor, recepção, validação dos parâmetros e resposta do handshake. |
| `client.py` | Socket do cliente, proposta do handshake, temporizador e retransmissão. |
| `testes.py` | Bateria de testes: sobe o servidor, roda os quatro grupos e confere os resultados. |

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
| `tipo` | Natureza do pacote: `HS`, `HSACK` (e, a partir do CP2, `DATA`, `ACK`, `NACK`). |
| `seq` | Número de sequência. No handshake é sempre `0`. |
| `checksum` | Soma dos códigos ASCII dos caracteres do **payload**. |
| `payload` | Conteúdo específico do tipo de pacote. |

O parsing usa `split("|", 3)`: no máximo 3 divisões, garantindo que um payload que
contenha `|` não seja picado (testado em A5).

### 2.2 Checksum

Algoritmo **ASCII**, implementado à mão (`protocol.calcular_checksum`), sem biblioteca
externa: soma de `ord(c)` para cada caractere do payload. É **fixo** para toda a
aplicação — não é negociado no handshake. Trocar de algoritmo (ex.: CRC16) exigiria
mudar os dois lados, e a função já levanta `ValueError` para algoritmo desconhecido.

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
cliente → servidor : HS|0|710|GBN,LOTE,30
servidor → cliente : HSACK|0|807|GBN,LOTE,30,5
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
3. Tipo diferente de `HS` nesta etapa → descartado, com log.
4. `modo_retransmissao` fora de {`GBN`, `SR`} ou `tipo_envio` fora de {`LOTE`, `IND`} → handshake recusado, sem resposta (o cliente cai no temporizador).
5. `tamanho_max_texto` < 30 → **ajustado para 30** e o valor efetivo volta no `HSACK`.
6. Caso válido → responde `HSACK` com os parâmetros efetivos + `tamanho_janela = 5`.

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
| Envio de dados | cada `MSG`, um de cada vez | `MSGACK` com o mesmo `seq` |

A contagem é **por pacote**: zera toda vez que um ACK chega. No envio de dados, uma
espera sem resposta acontece quando o tempo limite estoura ou quando o Windows devolve
`ConnectionResetError` (servidor fora do ar). Um `MSGACK` com `seq` diferente do esperado
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

Toda resposta que o cliente espera, tanto o `HSACK` quanto cada `MSGACK`, passa por uma
única função, `receber_resposta(sock, tipo, seq)`. Ela devolve o pacote só se ele passar
por **todas** as regras abaixo, na ordem. Qualquer outra coisa é descartada com uma linha
`Descartado: ...` e o cliente continua esperando dentro do mesmo prazo:

| # | Regra | O que barra |
| :--- | :--- | :--- |
| 1 | O datagrama cabe em `TAM_RECV` | datagrama gigante (`OSError` 10040 no Windows) |
| 2 | Veio do endereço do servidor (`HOST`, `PORTA`) | pacote forjado por outro programa ou outra porta |
| 3 | Decodifica em UTF-8 e tem os 4 campos, com `seq` e `checksum` numéricos | lixo, bytes binários, pacote incompleto |
| 4 | O checksum bate com o payload | pacote corrompido no caminho |
| 5 | O tipo e o `seq` são os esperados | ACK repetido, ACK de outro pacote, tipo trocado |

**Prazo fixo.** O tempo de espera é calculado uma vez (`agora + TIMEOUT_ENVIO`), e cada
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

---

## 3. Cobertura da tabela 3.1 (transporte confiável)

| Mecanismo | Situação no Checkpoint 1 |
| :--- | :--- |
| Soma de verificação | Calculada e transmitida em todo pacote. Conferida pelo servidor (`HS` e dados) e pelo cliente (`HSACK` e `MSGACK`); pacote com checksum errado é descartado. |
| Temporizador | Implementado no cliente (`TIMEOUT_ENVIO` = 1 s, `MAX_TENTATIVAS_ENVIO` = 5 tentativas por pacote). |
| Número de sequência | Campo existe no cabeçalho; vale `0` no handshake. Uso real no CP2. |
| Reconhecimento positivo | `HSACK` confirma o handshake. `ACK` de dados no CP2. |
| Reconhecimento negativo | Ainda não implementado (CP2/CP3). |
| Janela / paralelismo | Negociada (1–5, inicial 5). O uso efetivo da janela é do CP2. |

---

## 4. Manual de utilização

Requisito: **Python 3** (testado na 3.14). Nenhuma dependência externa.

**Terminal 1 — servidor:**

```bash
python3 server.py
```

**Terminal 2 — cliente (parâmetros default: GBN, LOTE, 30):**

```bash
python3 client.py
```

**Cliente escolhendo os parâmetros:**

```bash
python3 client.py --modo SR --envio IND --texto 77
python3 client.py --help
```

**Cliente informando a mensagem (primeiro argumento):**

```bash
python3 client.py "ola servidor"
python3 client.py "uma mensagem bem maior que trinta caracteres" --texto 50 --modo SR
```

| Argumento | Valores | Default |
| :--- | :--- | :--- |
| `mensagem` (posicional, 1º argumento) | texto entre aspas, de 1 até `--texto` caracteres | nenhuma (só faz o handshake) |
| `--modo` | `GBN`, `SR` | `GBN` |
| `--envio` | `LOTE`, `IND` | `LOTE` |
| `--texto` | inteiro ≥ 30 | `30` |

A mensagem é validada antes de qualquer envio: vazia ou maior que `--texto` faz o
cliente encerrar com erro do `argparse`, sem mandar nada para a rede. Como o servidor
só ajusta o `tamanho_max_texto` para cima (mínimo 30), uma mensagem que cabe no valor
proposto sempre cabe no valor confirmado no `HSACK`.

Host e porta ficam em `config.py` (`HOST = "127.0.0.1"`, `PORTA = 5000`); para rodar
entre máquinas diferentes, basta trocar o `HOST` para o IP do servidor.

---

## 5. Testes

Os testes estão separados em cinco blocos, do mais simples para o mais completo. A ideia
é que cada bloco responda uma pergunta diferente.

### Bloco A — o protocolo sozinho

Testa só o `protocol.py`, sem socket nenhum: montar um pacote, ler ele de volta, calcular
o checksum e montar/desmontar o HS e o HSACK. Serve para garantir que o formato
`tipo|seq|checksum|payload` está correto antes de envolver rede. Inclui o caso de um
payload que contém o próprio delimitador `|`, que é onde o parsing costuma quebrar.

**Pergunta que responde:** o protocolo, no papel, está certo?

### Bloco B — o handshake pela rede

Sobe o `server.py` e o `client.py` de verdade e faz os dois conversarem via UDP. Cobre o
handshake completo, vários clientes em sequência, o cliente escolhendo os parâmetros pela
linha de comando, a validação desses parâmetros antes do envio e o comportamento quando
não há servidor no ar (as 5 retransmissões). Cobre também o envio de uma mensagem, com
cada pacote confirmado antes do próximo (B6), uma mensagem com `|` e acentos (B7) e a
recusa de mensagens vazias, longas demais ou com caracteres que não viram UTF-8 (B8, B9).

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
mensagem clara e código 1, nunca com traceback e nunca travado. Cada caso está descrito
no [README.md](README.md).

**Pergunta que responde:** o cliente aguenta um servidor (ou uma rede) que se comporta mal?

### Como rodar

Tudo de uma vez, com o script subindo e derrubando o servidor sozinho:

```bash
python3 testes.py                 # todos os blocos
python3 testes.py --completo      # inclui o B4, que leva ~5s
python3 testes.py A               # so um bloco
python3 testes.py C1              # so um teste
python3 testes.py --silencioso    # so o veredito, sem a saida de cada teste
```

O script compara cada resultado com o esperado, imprime `[OK]`/`[FALHOU]` e, no fim,
mostra o log do servidor. Se já houver um servidor rodando na porta 5000, ele usa esse.

Para rodar um teste por vez na mão, os comandos de cada um estão no [README.md](README.md).

---

## 6. Processo de construção e uso de IA

### 6.1 Estratégia de aprendizado com IA

- Como a IA foi usada para entender GBN × SR e decidir pelo GBN como modo default.
- Como a IA ajudou a modelar a FSM do handshake e a desenhar o formato do pacote
  (`tipo|seq|checksum|payload`).
- Conceitos que ficaram mais claros com a explicação da IA (ACK cumulativo × individual,
  papel do temporizador, por que o receptor do GBN não precisa de buffer).

### 6.2 Análise crítica e debugging

Registrar aqui os casos em que a revisão do grupo pegou problema. Exemplos já
verificados neste checkpoint:

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



## 7. Limitações conhecidas / próximos passos

| Item | Checkpoint previsto |
| :--- | :--- |
| Cliente ainda não envia o `MSGFIM`, então o servidor não chega a montar a mensagem completa | CP2 |
| Cliente envia um pacote por vez (espera o ACK antes do próximo); a janela negociada ainda não é usada | CP2 |
| Uso efetivo do número de sequência e da janela (GBN e SR) no envio | CP2 |
| `LOTE` e `IND` são aceitos, mas ainda não mudam o comportamento do envio | CP2 |
| `NACK` de dados | CP2/CP3 |
| Inserção determinística de erros e perdas pelo cliente | CP3 |
| `VERSAO_PROTOCOLO` declarada mas ainda não usada no cabeçalho | CP2 |
| O checksum cobre só o payload: um `seq` ou `tipo` corrompido no caminho não é detectado | CP3 |
