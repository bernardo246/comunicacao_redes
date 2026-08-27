## documetação do uso de IA / relatorio:
<a href="https://docs.google.com/document/d/1sqhnJL_X32p5hlbgSm2kyc2LuHvbaiGpdfhAUgdukyc/edit?usp=sharing">
      <img src="https://img.shields.io/badge/Relatorio_Uso_IA-blue?style=for-the-badge&logo=google-docs&logoColor=white" />
</a>

- link do relatorio: ainda tem que ser criado



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