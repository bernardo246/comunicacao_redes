#criar cabeçalho + handshake

import argparse
import socket
from config import *
from protocol import montar_handshake_request, parsear_handshake, fragmentar_texto, montar_pacote_data

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



# Pega os argumentos que chegarem da linha de comando e retorna um objeto com os valores. Se algum argumento não for passado, usa o valor default.
def ler_argumentos():
    parser = argparse.ArgumentParser(description="Cliente do trabalho de redes - handshake (checkpoint 1).")
    # primeiro argumento (posicional): a mensagem a ser enviada. E opcional, sem ela o cliente so faz o handshake
    parser.add_argument("mensagem", nargs="?", default=None,
                        help="texto a ser enviado ao servidor; use aspas se tiver espaco (opcional)")
    parser.add_argument("--modo", choices=[GBN, SR], default=MODO_PADRAO,
                        help=f"modo de retransmissao (default: {MODO_PADRAO})")
    parser.add_argument("--envio", choices=[MODO_LOTE, MODO_INDIVIDUAL], default=ENVIO_PADRAO,
                        help=f"tipo de envio (default: {ENVIO_PADRAO})")
    parser.add_argument("--texto", type=int, default=MAX_TEXTO_DEFAULT,
                        help=f"tamanho maximo do texto, minimo {MIN_TEXTO} (default: {MAX_TEXTO_DEFAULT})")
    args = parser.parse_args()

    if args.texto < MIN_TEXTO:
        parser.error(f"--texto deve ser no minimo {MIN_TEXTO} (recebido {args.texto})")

    # a mensagem nao pode passar do tamanho maximo que o cliente vai propor no handshake
    if args.mensagem is not None:
        if args.mensagem == "":
            parser.error("a mensagem nao pode ser vazia")
        if len(args.mensagem) > args.texto:
            parser.error(f"a mensagem tem {len(args.mensagem)} caracteres, acima do limite de {args.texto} (use --texto para aumentar)")
    return args


def enviar_mensagem(sock, mensagem):
    fragmentos = fragmentar_texto(mensagem) # quebra a mensagem em pedacos de ate 4 caracteres
    print("Fragmentos da mensagem:", fragmentos)

    for seq, fragmento in enumerate(fragmentos): # seq comeca em 0 e acompanha a posicao do fragmento na lista
        pacote = montar_pacote_data(seq, fragmento) # coloca o cabecalho tipo|seq|checksum na frente do fragmento
        sock.sendto(pacote.encode(ENCODING), (HOST, PORTA)) # mesmo socket do handshake, para o servidor achar a sessao
        print("Pacote enviado:", pacote)




def main():
    args = ler_argumentos()
    sock, config_sessao = enviar_handshake(args.modo, args.envio, args.texto)
    print ("Configuração da sessão:", config_sessao)

    if args.mensagem is not None:
        enviar_mensagem(sock, args.mensagem)


    sock.close()
        



if __name__ == "__main__":
    main()
