#criar cabeçalho + handshake

import socket
from config import *
from protocol import montar_handshake_request, parsear_handshake



def enviar_handshake_padrao():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) #definindo que é udp e criando o socket
    handshake = montar_handshake_request(MODO_PADRAO, ENVIO_PADRAO, MAX_TEXTO_DEFAULT) #montando o pacote de handshake
    sock.sendto(handshake.encode(ENCODING), (HOST, PORTA)) #enviando o pacote para o servidor
    return sock

