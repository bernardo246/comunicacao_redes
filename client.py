#criar cabeçalho + handshake

import argparse
import socket
from config import *
from protocol import montar_handshake_request, parsear_handshake

MAX_TENTATIVAS = 5

""" 
OBS: so tem que deixar essa função ser mais maleavel, sendo possivel escolher gbn ou sr, lote ou individual
e a quantidade de texto, mas se n inserir usa o padrão default
"""
def enviar_handshake(modo_retransmissao=MODO_PADRAO, tipo_envio=ENVIO_PADRAO, tamanho_max_texto=MAX_TEXTO_DEFAULT):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # criando socket e definindo que é udp
    sock.settimeout(5) # definindo o tempo limite de espera para receber a resposta do servidor (em segundos)

    handshake = montar_handshake_request(modo_retransmissao, tipo_envio, tamanho_max_texto) #criando o handshake padrao
    print("Handshake proposto ao servidor:", handshake)

    tentativas = 0 # isso diz quantas vezes o cliente tentou enviar o handshake e não recebeu resposta do servidor
    while tentativas < MAX_TENTATIVAS: # limitei em 5 vezes pra ele nao ficar tentando infinitamente
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
        sock.close()
        exit(1)

    config_sessao = parsear_handshake(resposta) #retorna um dicionario com os parametros do handshake
    print("Handshake confirmado pelo servidor:", config_sessao)

    if config_sessao["tamanho_max_texto"] != tamanho_max_texto:
        print(f"Aviso: o servidor ajustou o tamanho maximo de {tamanho_max_texto} para {config_sessao['tamanho_max_texto']}.")

    return sock, config_sessao #retorna o socket e o dicionario com os parametros do handshake


def enviar_handshake_padrao():
    return enviar_handshake()


def ler_argumentos():
    parser = argparse.ArgumentParser(description="Cliente do trabalho de redes - handshake (checkpoint 1).")
    parser.add_argument("--modo", choices=[GBN, SR], default=MODO_PADRAO,
                        help=f"modo de retransmissao (default: {MODO_PADRAO})")
    parser.add_argument("--envio", choices=[MODO_LOTE, MODO_INDIVIDUAL], default=ENVIO_PADRAO,
                        help=f"tipo de envio (default: {ENVIO_PADRAO})")
    parser.add_argument("--texto", type=int, default=MAX_TEXTO_DEFAULT,
                        help=f"tamanho maximo do texto, minimo {MIN_TEXTO} (default: {MAX_TEXTO_DEFAULT})")
    args = parser.parse_args()

    if args.texto < MIN_TEXTO:
        parser.error(f"--texto deve ser no minimo {MIN_TEXTO} (recebido {args.texto})")
    return args


def main():
    args = ler_argumentos()
    sock, config_sessao = enviar_handshake(args.modo, args.envio, args.texto)
    print ("Configuração da sessão:", config_sessao)
    

    sock.close()
        

if __name__ == "__main__":
    main()
