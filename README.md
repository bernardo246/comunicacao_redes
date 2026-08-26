## etapa 1

## definição do modelo de comportamento de trasmissão e recepção de pacotes e seu gerenciamento

| Aspecto | Go-Back-N (GBN) | Repetição Seletiva (SR) |
| :--- | :--- | :--- |
| **Buffer no Receptor** | **Não exige** (descarta pacotes fora de ordem)[cite: 1]. | **Exige** (armazena pacotes fora de ordem temporariamente). |
| **Confirmação (ACK)** | **Cumulativa** (confirma "até o pacote X"). | **Individual** (confirma "o pacote X especificamente"). |
| **Temporizadores (*Timers*)** | **1 único temporizador** para o pacote mais antigo não confirmado[cite: 1]. | **1 temporizador individual** para cada pacote enviado na janela. |
| **Retransmissão** | Retransmite o pacote perdido **e todos os subsequentes** da janela. | Retransmite **apenas o pacote específico** que falhou ou expirou. |
| **Complexidade** | Mais simples de implementar no código. | Mais complexo (exige gestão de múltiplos timers e alocação de buffer). |
| **Uso da Banda** | Menos eficiente em canais com alta taxa de perdas (desperdício de tráfego). | Mais eficiente em canais com perdas (envia apenas o que é estritamente necessário). |