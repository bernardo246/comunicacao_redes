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
DELIM_CAMPO = "|"         #
DELIM_QUADRO = "\n"       # delimitador de quadro sobre o fluxo de bytes do TCP

# Carga util maxima de um pacote de DADOS (exigencia do enunciado).
# Mensagens de controle (handshake) nao carregam texto do usuario e por isso
# nao estao sujeitas a esse limite.
MAX_PAYLOAD = 4

# ---------------------------------------------------------------- negociacao
MIN_TEXTO = 30            # limite minimo exigido pelo enunciado
MAX_TEXTO_DEFAULT = 30    # valor default proposto pelo cliente

JANELA_MIN = 1
JANELA_MAX = 5
JANELA_INICIAL = 5        # valor inicial determinado pelo servidor

MODO = "GBN-LOTE"