# Relatório — Trabalho I (Comunicação e Redes)

> Documento incremental: evolui a cada checkpoint, conforme exigido na especificação.
> **Status atual: Checkpoint 1 — Handshake & Sockets (entrega em 09/09/2026).**

## 1. Identificação

| Campo | Conteúdo |
| :--- | :--- |
| Disciplina | Comunicação e Redes |
| Trabalho | Trabalho I — Transporte confiável na camada de aplicação |
| Grupo | *(preencher com os nomes dos integrantes)* |
| Monitor(a) | *(preencher)* |
| Repositório | *(preencher com o link do repositório)* |

---

## 2. Visão geral da aplicação

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

## 3. Especificação do protocolo

### 3.1 Formato do pacote

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

### 3.2 Checksum

Algoritmo **ASCII**, implementado à mão (`protocol.calcular_checksum`), sem biblioteca
externa: soma de `ord(c)` para cada caractere do payload. É **fixo** para toda a
aplicação — não é negociado no handshake. Trocar de algoritmo (ex.: CRC16) exigiria
mudar os dois lados, e a função já levanta `ValueError` para algoritmo desconhecido.

### 3.3 Handshake (Checkpoint 1)

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

### 3.4 Parâmetros negociados

| Parâmetro | Valores | Quem decide |
| :--- | :--- | :--- |
| `modo_retransmissao` | `GBN` (Go-Back-N) ou `SR` (Repetição Seletiva) | Proposto pelo cliente, validado pelo servidor |
| `tipo_envio` | `LOTE` ou `IND` (individual) | Proposto pelo cliente, validado pelo servidor |
| `tamanho_max_texto` | inteiro ≥ 30 (`MIN_TEXTO`), default 30 | Proposto pelo cliente, **corrigido** pelo servidor se abaixo do mínimo |
| `tamanho_janela` | 1 a 5, inicial 5 | **Só o servidor**, aparece apenas no `HSACK` |

O `tamanho_janela` não vai no `HS`: pelo enunciado, a janela é a janela de recepção do
servidor e é ele quem a determina. O cliente descobre o valor ao ler o `HSACK`.

### 3.5 Regras de decisão do servidor

1. Datagrama que não decodifica em UTF-8 → descartado, com log.
2. Pacote fora do formato de 4 campos → descartado, com log (`ValueError`/`IndexError` tratados).
3. Tipo diferente de `HS` nesta etapa → descartado, com log.
4. `modo_retransmissao` fora de {`GBN`, `SR`} ou `tipo_envio` fora de {`LOTE`, `IND`} → handshake recusado, sem resposta (o cliente cai no temporizador).
5. `tamanho_max_texto` < 30 → **ajustado para 30** e o valor efetivo volta no `HSACK`.
6. Caso válido → responde `HSACK` com os parâmetros efetivos + `tamanho_janela = 5`.

Em nenhuma hipótese um pacote inválido derruba o servidor: o laço principal trata as
exceções por datagrama e segue atendendo.

### 3.6 Temporizador e retransmissão (lado cliente)

O cliente usa `settimeout(5)` e reenvia o `HS` até **5 vezes**. Se as 5 tentativas
expirarem, ele informa o erro e sai com código 1. É a primeira das características de
transporte confiável exigidas pela tabela 3.1 do livro a aparecer no código.

### 3.7 Máquina de estados (FSM) do handshake

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

---

## 4. Cobertura da tabela 3.1 (transporte confiável)

| Mecanismo | Situação no Checkpoint 1 |
| :--- | :--- |
| Soma de verificação | Calculada e transmitida em todo pacote. **Ainda não é conferida** no destino (previsto para o CP2/CP3). |
| Temporizador | Implementado no cliente (5 s, 5 tentativas). |
| Número de sequência | Campo existe no cabeçalho; vale `0` no handshake. Uso real no CP2. |
| Reconhecimento positivo | `HSACK` confirma o handshake. `ACK` de dados no CP2. |
| Reconhecimento negativo | Ainda não implementado (CP2/CP3). |
| Janela / paralelismo | Negociada (1–5, inicial 5). O uso efetivo da janela é do CP2. |

---

## 5. Manual de utilização

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

| Flag | Valores | Default |
| :--- | :--- | :--- |
| `--modo` | `GBN`, `SR` | `GBN` |
| `--envio` | `LOTE`, `IND` | `LOTE` |
| `--texto` | inteiro ≥ 30 | `30` |

Host e porta ficam em `config.py` (`HOST = "127.0.0.1"`, `PORTA = 5000`); para rodar
entre máquinas diferentes, basta trocar o `HOST` para o IP do servidor.

---

## 6. Testes

Os testes estão separados em quatro blocos, do mais simples para o mais completo. A ideia
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
não há servidor no ar (as 5 retransmissões).

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

### Como rodar

Tudo de uma vez, com o script subindo e derrubando o servidor sozinho:

```bash
python3 testes.py                 # todos os blocos
python3 testes.py --completo      # inclui o B4, que leva ~25s
python3 testes.py A               # so um bloco
python3 testes.py C1              # so um teste
python3 testes.py --silencioso    # so o veredito, sem a saida de cada teste
```

O script compara cada resultado com o esperado, imprime `[OK]`/`[FALHOU]` e, no fim,
mostra o log do servidor. Se já houver um servidor rodando na porta 5000, ele usa esse.

Para rodar um teste por vez na mão, os comandos de cada um estão no [README.md](README.md).

---

## 7. Processo de construção e uso de IA

### 7.1 Estratégia de aprendizado com IA

*(preencher pelo grupo — sugestão de roteiro:)*

- Como a IA foi usada para entender GBN × SR e decidir pelo GBN como modo default.
- Como a IA ajudou a modelar a FSM do handshake e a desenhar o formato do pacote
  (`tipo|seq|checksum|payload`).
- Conceitos que ficaram mais claros com a explicação da IA (ACK cumulativo × individual,
  papel do temporizador, por que o receptor do GBN não precisa de buffer).

### 7.2 Análise crítica e debugging

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
   que o cliente **não** trata, e o laço de retransmissão não chega a rodar. No Linux, o
   mesmo cenário caiu em `socket.timeout` e as 5 retransmissões aconteceram normalmente.
   *Pendência assumida:* tratar `ConnectionResetError` junto com `socket.timeout`.

*(Acrescentar aqui os casos em que a IA sugeriu algo incorreto e como o grupo percebeu.)*

### 7.3 Prompt log

*(preencher: links das conversas ou anexo com os principais prompts usados na
arquitetura, na implementação e nos testes.)*

---

## 8. Limitações conhecidas / próximos passos

| Item | Checkpoint previsto |
| :--- | :--- |
| Checksum é enviado mas não conferido no destino | CP2/CP3 |
| Fragmentação do texto em payloads de no máximo 4 caracteres (`MAX_PAYLOAD`) | CP2 |
| Uso efetivo do número de sequência e da janela (GBN e SR) | CP2 |
| `ACK` / `NACK` de dados e impressão dos metadados no servidor | CP2 |
| Inserção determinística de erros e perdas pelo cliente | CP3 |
| Cliente não trata `ConnectionResetError` (Windows, servidor fora do ar) | CP2 |
| Cliente não confere o checksum do `HSACK` nem valida se a janela está entre 1 e 5 | CP2 |
| `VERSAO_PROTOCOLO` declarada mas ainda não usada no cabeçalho | CP2 |
