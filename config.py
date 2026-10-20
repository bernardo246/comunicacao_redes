"""
Constantes de configuracao da aplicacao.

Centralizar tudo aqui evita numeros magicos espalhados pelo codigo e facilita
a demonstracao (basta trocar um valor e reexecutar).
"""

# ---------------------------------------------------------------- rede
HOST = "127.0.0.1"        # localhost; trocar por um IP para rodar entre maquinas
PORTA = 5000
TAM_RECV = 1024           # bytes lidos por chamada de recv()
ENCODING = "utf-8"

# ---------------------------------------------------------------- protocolo
VERSAO_PROTOCOLO = 1
DELIM_CAMPO = "|"         
DELIM_PAYLOAD =","

TYPE_DATA="MSG"
TYPE_DATA_ACK="MSGACK"
TYPE_FIM="MSGFIM"         # ultimo pacote da mensagem (payload vazio), sinaliza o fim

TYPE_HANDSHAKE_REQ = "HS"
TYPE_HANDSHAKE_ACK = "HSACK"


# Carga util maxima de um pacote de DADOS (exigencia do enunciado).
# Mensagens de controle (handshake) nao carregam texto do usuario e por isso
# nao estao sujeitas a esse limite.
MAX_PAYLOAD = 4

# ---------------------------------------------------------------- negociacao
MIN_TEXTO = 30            # limite minimo exigido pelo enunciado
MAX_TEXTO_DEFAULT = 30    # valor default proposto pelo cliente

# quantidade de pacotes que foram enviados por lote
JANELA_MIN = 1
JANELA_MAX = 5
JANELA_INICIAL = 5        # valor inicial determinado pelo servidor

# ---------------------------------------------------------------- retransmissao (cliente)
# Quantas vezes o cliente envia o mesmo pacote sem receber resposta antes de desistir.
# Vale para o HS (esperando o HSACK) e para cada pacote de dados (esperando o MSGACK).
# A contagem e por pacote: zera sempre que um ACK chega.
MAX_TENTATIVAS_ENVIO = 5

# Tempo (em segundos) que o cliente espera a resposta de um pacote antes de reenviar.
# Em localhost a resposta chega em milissegundos, entao 1s ja e folga de sobra.
# Entre maquinas diferentes, aumentar se aparecerem retransmissoes sem perda real.
TIMEOUT_ENVIO = 1

# ---------------------------------------------------------------- handshake

# valores possiveis para o modo de retransmissao
GBN = "GBN"               # Go-Back-N
SR  = "SR"                # Repeticao Seletiva

# valores possiveis para o tipo de envio
MODO_LOTE = "LOTE"
MODO_INDIVIDUAL = "IND"

# valores possiveis para o algoritmo de checksum
CHECKSUM_ASCII = "Ascii"

# padroes usados pelo cliente ao propor o handshake
MODO_PADRAO = GBN                          # retransmissao: GBN ou SR
ENVIO_PADRAO = MODO_LOTE                   # envio: LOTE ou INDIVIDUAL
ALGORITMO_CHECKSUM_PADRAO = CHECKSUM_ASCII # algoritmo do checksum