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
def montar_pacote(tipo, seq, checksum, payload):
    # Monta a string final do pacote a partir dos campos do cabeçalho + payload.
    pacote = DELIM_CAMPO.join([tipo, str(seq), str(checksum), payload])
    return pacote

def parsear_pacote(pacote):
    #Quebra um pacote recebido em seus campos de cabeçalho + payload.
    tipo, seq, checksum, payload = pacote.split(DELIM_CAMPO, 3)
    return {
        "tipo": tipo,
        "seq": int(seq),
        "checksum": checksum,
        "payload": payload,
    }

def montar_handshake_request(modo, algoritmo, tamanho_max_texto):
    """Cliente -> servidor: propõe modo, algoritmo e tamanho máximo do texto."""
    payload = DELIM_PAYLOAD.join([modo, algoritmo, str(tamanho_max_texto)])
    return montar_pacote(TYPE_HANDSHAKE_REQ, 0, "0", payload)

def montar_handshake_ack(modo, algoritmo, tamanho_max_texto, tamanho_janela):
    """Servidor -> cliente: confirma os parâmetros e informa o tamanho da janela."""
    payload = DELIM_PAYLOAD.join([modo, algoritmo, str(tamanho_max_texto), str(tamanho_janela)])
    return montar_pacote(TYPE_HANDSHAKE_ACK, 0, "0", payload)

# aqui tem que fazer o parse do handshake 