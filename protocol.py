# montar as regras de comunicação + pacote
from config import *
"""
Formato de todo pacote: tipo|seq|checksum|payload
- tipo: identifica a natureza do pacote (handshake, dado, ack, ...)
- seq: número de sequência (0 no handshake, ainda não é usado)
- checksum: soma dos códigos ASCII do payload (ver calcular_checksum)
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

# Checagem de integridade, implementada à mão (sem biblioteca externa)
def calcular_checksum(algoritmo,payload):
    '''
    Calcula o checksum de um payload (string), usado para detectar corrupção no caminho.

    Algoritmo "Ascii": soma o código de cada caractere do payload (ord).
    Ex.: "ABC" -> 65 + 66 + 67 = 198. Payload vazio -> 0.

    Quem envia grava o resultado no cabeçalho do pacote; quem recebe recalcula sobre o
    payload que chegou e compara. Se os valores forem diferentes, o pacote foi alterado e
    deve ser descartado.
    '''

    if algoritmo == CHECKSUM_ASCII:
        soma = 0                 # acumulador da soma dos códigos
        for c in payload:        # percorre o payload caractere a caractere
            soma += ord(c)       # ord() devolve o código numérico do caractere
        return soma
    else:
        raise ValueError("Algoritmo de checksum não suportado")

#criptografia simetrica, implementada à mão (sem biblioteca externa)
def criptografia_simetrica(chave, dados):
    '''
    Cifra de fluxo RC4. Recebe a chave (str) e os dados (bytes) e devolve os dados
    transformados (bytes). Cifrar e decifrar são a mesma operação: aplicar a função duas
    vezes com a mesma chave devolve o original.

    Ex.: chave "Key", dados b"Plaintext" -> bytes cujo hex é "bbf316e8d940af0ad3".
    '''
    chave_bytes = list(chave.encode("utf-8"))   # a chave vira lista de números 0..255
    if len(chave_bytes) == 0:
        raise ValueError("A chave de criptografia não pode ser vazia")

    # KSA: embaralha a lista S de 256 posições usando a chave
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + chave_bytes[i % len(chave_bytes)]) % 256
        S[i], S[j] = S[j], S[i]

    # PRGA: gera um byte do keystream por byte de dados e combina com XOR
    i = 0
    j = 0
    resultado = []
    for byte in dados:
        i = (i + 1) % 256
        j = (j + S[i]) % 256
        S[i], S[j] = S[j], S[i]
        k = S[(S[i] + S[j]) % 256]    # byte do keystream
        resultado.append(byte ^ k)

    return bytes(resultado)

def cifrar_mensagem(chave, texto):
    '''
    Cifra o texto inteiro com RC4 e devolve o resultado como string (str), com um
    caractere por byte cifrado (chr): o tamanho cifrado é igual ao dos bytes do texto,
    sem dobrar a quantidade de pacotes.

    Cada caractere do resultado tem código de 0 a 255 e pode ser qualquer um deles,
    inclusive o delimitador "|" (o parsear_pacote preserva o "|" dentro do payload).
    Deve ser chamada antes de fragmentar a mensagem em pacotes.

    Ex.: chave "Key", texto "Plaintext" -> 9 caracteres, de códigos 187, 243, 22, ...
    '''
    cifrados = criptografia_simetrica(chave, texto.encode("utf-8"))
    return "".join(chr(byte) for byte in cifrados)

def decifrar_mensagem(chave, texto_cifrado):
    '''
    Operação inversa de cifrar_mensagem: recebe a string cifrada já remontada, converte cada
    caractere de volta para byte (ord), decifra com RC4 e devolve o texto original (str).

    Levanta ValueError se algum caractere tiver código acima de 255 (não pode ter saído de
    cifrar_mensagem) ou se o resultado não for UTF-8 válido (costuma indicar chave errada).
    '''
    codigos = [ord(c) for c in texto_cifrado]
    for codigo in codigos:
        if codigo > 255:
            raise ValueError("Caractere fora do intervalo 0-255 no texto cifrado")
    return criptografia_simetrica(chave, bytes(codigos)).decode("utf-8")


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
        lista_de_payload.append(pedaco)
    return lista_de_payload

def montar_pacote_data(seq,payload):
    checksum = calcular_checksum(ALGORITMO_CHECKSUM_PADRAO, payload)
    pacote= montar_pacote(TYPE_DATA,seq,checksum,payload)
    return pacote

def montar_pacote_fim(seq):
    """Pacote de payload vazio que sinaliza o fim da mensagem; entra na fila como um DATA qualquer."""
    checksum = calcular_checksum(ALGORITMO_CHECKSUM_PADRAO, "")
    return montar_pacote(TYPE_FIM, seq, checksum, "")

def montar_pacotes_mensagem(texto):
    """Fragmenta o texto e devolve a lista de pacotes, com o pacote FIM na última posição."""
    pacotes = []
    for seq, pedaco in enumerate(fragmentar_texto(texto)):
        pacotes.append(montar_pacote_data(seq, pedaco))
    pacotes.append(montar_pacote_fim(len(pacotes)))
    return pacotes

def parsear_pacote_data(pacote_bruto):
    pacote = parsear_pacote(pacote_bruto)
    checksum_esperado = calcular_checksum(ALGORITMO_CHECKSUM_PADRAO, pacote["payload"])
    pacote["checksum_valido"] = (checksum_esperado == pacote["checksum"])
    pacote["ultimo"] = (pacote["tipo"] == TYPE_FIM)  # sinal de fim de mensagem para o server/client
    return pacote

def montar_ack(seq):
    checksum = calcular_checksum(ALGORITMO_CHECKSUM_PADRAO, "")
    return montar_pacote(TYPE_DATA_ACK, seq, checksum, "")

def parsear_ack(packege):
    return parsear_pacote(packege)

