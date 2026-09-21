# montar as regras de comunicação + pacote
from config import *
"""
Formato de todo pacote: tipo|seq|checksum|payload
- tipo: identifica a natureza do pacote (handshake, dado, ack, ...)
- seq: número de sequência (0 no handshake, ainda não é usado)
- checksum: placeholder por enquanto ("0"), vira campo real no checkpoint 3
- payload: conteúdo específico do tipo de pacote
 
No handshake, o payload carrega os parâmetros da sessão, separados por vírgula:
modo,algoritmo,tamanho_max_texto[,tamanho_janela]
"""


# Funções base
def montar_pacote(tipo, seq, checksum, payload):
    # Monta a string final do pacote a partir dos campos do cabeçalho + payload.
    pacote = DELIM_CAMPO.join([tipo, str(seq), str(checksum), payload])
    return pacote

def parsear_pacote(pacote):
    #Quebra um pacote recebido em seus campos de cabeçalho + payload.
    tipo, seq, checksum, payload = pacote.split(DELIM_CAMPO, 3) # esse 3 delimita o número máximo de splits, garantindo que o payload possa conter o delimitador
    return {
        "tipo": tipo,
        "seq": int(seq),
        "checksum": int(checksum),
        "payload": payload,
    }

# calcula o checksum de um payload (string) somando os códigos ASCII de cada caractere
def calcular_checksum(algoritmo,payload):
    '''por enquanto só implementa o algoritmo Ascii, que soma os códigos ASCII de cada caractere do payload.'''

    if algoritmo == "Ascii":
        soma = 0
        for c in payload:
            soma += ord(c)
        return soma
    else:
        raise ValueError("Algoritmo de checksum não suportado")


# Funções de handshake
def montar_handshake_request(modo_retransmissao, tipo_envio, tamanho_max_texto):
    """Cliente -> servidor: propõe modo de retransmissão, tipo de envio e tamanho máximo do texto."""
    payload = DELIM_PAYLOAD.join([modo_retransmissao, tipo_envio, str(tamanho_max_texto)])
    checksum = calcular_checksum(ALGORITMO_CHECKSUM_PADRAO, payload)  # mensagens de controle tambem precisam de checksum, mesmo que nao carreguem texto do usuario
    return montar_pacote(TYPE_HANDSHAKE_REQ, 0, checksum, payload)

def montar_handshake_ack(modo_retransmissao, tipo_envio, tamanho_max_texto, tamanho_janela):
    """Servidor -> cliente: confirma os parâmetros e informa o tamanho da janela."""
    payload = DELIM_PAYLOAD.join([modo_retransmissao, tipo_envio, str(tamanho_max_texto), str(tamanho_janela)])
    checksum = calcular_checksum(ALGORITMO_CHECKSUM_PADRAO, payload)
    return montar_pacote(TYPE_HANDSHAKE_ACK, 0, checksum, payload)

def parsear_handshake(bruto):
    """Extrai os campos de uma mensagem de handshake (request ou ack)."""
    pacote = parsear_pacote(bruto)
    campos = pacote["payload"].split(DELIM_PAYLOAD)

    resultado = {
        "tipo": pacote["tipo"],
        "modo_retransmissao": campos[0],
        "tipo_envio": campos[1],
        "tamanho_max_texto": int(campos[2]),
    }

    if pacote["tipo"] == TYPE_HANDSHAKE_ACK:
        resultado["tamanho_janela"] = int(campos[3])
    return resultado


def fragmentar_texto(string):
    lista_de_payload=[]
    for i in range(0,len(string),4):
        pedaco=string[i:i+4]
        lista_de_payload[i].append(pedaco)
    return lista_de_payload