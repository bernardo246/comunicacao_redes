#criar cabeçalho + handshake

import socket
from config import *
from protocol import montar_handshake_request, parsear_handshake



def enviar_handshake_padrao():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # criando socket e definindo que é udp
    sock.settimeout(5) # definindo o tempo limite de espera para receber a resposta do servidor (em segundos)

    handshake = montar_handshake_request(MODO_PADRAO, ENVIO_PADRAO, MAX_TEXTO_DEFAULT) #criando o handshake padrao

    tentativas = 0 # isso diz quantas vezes o cliente tentou enviar o handshake e não recebeu resposta do servidor
    while tentativas < 5: # limitei em 5 vezes pra ele nao ficar tentando infinitamente
        sock.sendto(handshake.encode(ENCODING), (HOST, PORTA)) # envia o handshake para o servidor
        tentativas += 1
        try:
            dados, endereco_servidor = sock.recvfrom(TAM_RECV) 
            resposta = dados.decode(ENCODING) 
            break
        except socket.timeout:
            print(f"Tentativa {tentativas}: tempo limite excedido, tentando de novo...")
    else:
        print("Erro: número máximo de tentativas de handshake excedido.")
        exit(1)

    config_sessao = parsear_handshake(resposta) #retorna um dicionario com os parametros do handshake
    print("Handshake confirmado pelo servidor:", config_sessao)
    return sock, config_sessao #retorna o socket e o dicionario com os parametros do handshake



def main():
    sock, config_sessao = enviar_handshake_padrao()
    print ("Configuração da sessão:", config_sessao)
    

    sock.close()
        

    
    

