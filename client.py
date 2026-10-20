#criar cabeçalho + handshake

import argparse
import socket
import sys
import time
from config import *
from protocol import montar_handshake_request, parsear_handshake, fragmentar_texto, montar_pacote_data, parsear_pacote, calcular_checksum

"""
OBS: so tem que deixar essa função ser mais maleavel, sendo possivel escolher gbn ou sr, lote ou individual
e a quantidade de texto, mas se n inserir usa o padrão default
"""
def enviar_handshake(modo_retransmissao=MODO_PADRAO, tipo_envio=ENVIO_PADRAO, tamanho_max_texto=MAX_TEXTO_DEFAULT):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # criando socket e definindo que é udp

    handshake = montar_handshake_request(modo_retransmissao, tipo_envio, tamanho_max_texto) #criando o handshake padrao
    print("Handshake proposto ao servidor:", handshake)

    tentativas = 0 # isso diz quantas vezes o cliente tentou enviar o handshake e não recebeu resposta do servidor
    while tentativas < MAX_TENTATIVAS_ENVIO: # limite vem do config.py, pra ele nao ficar tentando infinitamente
        sock.sendto(handshake.encode(ENCODING), (HOST, PORTA)) # envia o handshake para o servidor
        tentativas += 1
        resposta = receber_resposta(sock, TYPE_HANDSHAKE_ACK, 0) # so aceita um HSACK valido vindo do servidor
        if resposta is not None:
            break
        print(f"Tentativa {tentativas}: sem resposta valida do servidor, tentando de novo...")
    else:
        encerrar_com_erro(sock, "número máximo de tentativas de handshake excedido.")

    try:
        config_sessao = parsear_handshake(resposta) #retorna um dicionario com os parametros do handshake
    except (ValueError, IndexError) as erro: # checksum certo mas payload faltando campo ou com numero invalido
        encerrar_com_erro(sock, f"HSACK malformado ({erro}).")

    problema = validar_hsack(config_sessao, modo_retransmissao, tipo_envio)
    if problema is not None:
        encerrar_com_erro(sock, f"HSACK recusado: {problema}.")
    print("Handshake confirmado pelo servidor:", config_sessao)

    if config_sessao["tamanho_max_texto"] != tamanho_max_texto:
        print(f"Aviso: o servidor ajustou o tamanho maximo de {tamanho_max_texto} para {config_sessao['tamanho_max_texto']}.")

    return sock, config_sessao #retorna o socket e o dicionario com os parametros do handshake


# confere se o servidor confirmou o que foi pedido e se a janela esta dentro do permitido. Retorna o problema ou None
def validar_hsack(config_sessao, modo_retransmissao, tipo_envio):
    if config_sessao["modo_retransmissao"] != modo_retransmissao:
        return f"modo {config_sessao['modo_retransmissao']} diferente do proposto ({modo_retransmissao})"
    if config_sessao["tipo_envio"] != tipo_envio:
        return f"tipo de envio {config_sessao['tipo_envio']} diferente do proposto ({tipo_envio})"
    if config_sessao["tamanho_max_texto"] < MIN_TEXTO:
        return f"tamanho maximo {config_sessao['tamanho_max_texto']} abaixo do minimo ({MIN_TEXTO})"
    if not JANELA_MIN <= config_sessao["tamanho_janela"] <= JANELA_MAX:
        return f"janela {config_sessao['tamanho_janela']} fora da faixa {JANELA_MIN} a {JANELA_MAX}"
    return None


# Pega os argumentos que chegarem da linha de comando e retorna um objeto com os valores. Se algum argumento não for passado, usa o valor default.
def ler_argumentos():
    parser = argparse.ArgumentParser(description="Cliente do trabalho de redes - handshake e envio de mensagem.")
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
        try:
            args.mensagem.encode(ENCODING) # o terminal pode entregar caracteres que nao viram bytes (ex.: surrogates no Windows)
        except UnicodeEncodeError:
            parser.error(f"a mensagem tem caracteres que nao podem ser codificados em {ENCODING}")
    return args


# espera ate TIMEOUT_ENVIO por um pacote do tipo e seq esperados. Retorna o pacote (string) ou None se o prazo acabar.
# Qualquer outra coisa que chegar no meio do caminho e descartada, sem derrubar o cliente.
def receber_resposta(sock, tipo_esperado, seq_esperado):
    servidor = (socket.gethostbyname(HOST), PORTA) # recvfrom devolve o IP, entao compara com o IP do HOST
    prazo = time.monotonic() + TIMEOUT_ENVIO # prazo fixo: pacotes errados chegando nao renovam o tempo de espera

    while True:
        restante = prazo - time.monotonic()
        if restante <= 0:
            return None
        sock.settimeout(restante)

        try:
            dados, endereco = sock.recvfrom(TAM_RECV)
        except (socket.timeout, ConnectionResetError): # no Windows, servidor fora do ar vira ConnectionResetError em vez de timeout
            return None
        except OSError as erro: # ex.: datagrama maior que TAM_RECV (WinError 10040 no Windows)
            print(f"Descartado: datagrama invalido ({erro})")
            continue

        if endereco != servidor:
            print(f"Descartado: pacote de {endereco}, que nao e o servidor")
            continue

        try:
            bruto = dados.decode(ENCODING)
            pacote = parsear_pacote(bruto)
        except (UnicodeDecodeError, ValueError) as erro: # bytes que nao sao texto ou pacote fora do formato tipo|seq|checksum|payload
            print(f"Descartado: pacote malformado ({erro})")
            continue

        if calcular_checksum(ALGORITMO_CHECKSUM_PADRAO, pacote["payload"]) != pacote["checksum"]:
            print("Descartado: checksum invalido:", bruto)
            continue

        if pacote["tipo"] != tipo_esperado or pacote["seq"] != seq_esperado:
            print("Descartado: nao e o esperado:", bruto) # ex.: ACK repetido de um pacote anterior
            continue

        return bruto


def enviar_mensagem(sock, mensagem):
    fragmentos = fragmentar_texto(mensagem) # quebra a mensagem em pedacos de ate 4 caracteres
    print("Fragmentos da mensagem:", fragmentos)

    indice = 0 # posicao do fragmento atual na lista, e tambem o seq do pacote
    tentativas = 0
    while indice < len(fragmentos): # so passa para o proximo fragmento quando o atual for confirmado
        pacote = montar_pacote_data(indice, fragmentos[indice]) # coloca o cabecalho tipo|seq|checksum na frente do fragmento
        sock.sendto(pacote.encode(ENCODING), (HOST, PORTA)) # mesmo socket do handshake, para o servidor achar a sessao
        print("Pacote enviado:", pacote)

        if receber_resposta(sock, TYPE_DATA_ACK, indice) is not None:
            print(f"ACK do seq={indice} recebido")
            indice += 1
            tentativas = 0 # zera para o proximo pacote
        else:
            tentativas += 1
            if tentativas == MAX_TENTATIVAS_ENVIO:
                encerrar_com_erro(sock, f"o seq={indice} nao foi confirmado depois de {MAX_TENTATIVAS_ENVIO} tentativas.")
            print(f"Tentativa {tentativas}: sem ACK do seq={indice}, reenviando...")


def encerrar_com_erro(sock, motivo):
    print("Erro:", motivo)
    sock.close()
    sys.exit(1) # sys.exit em vez de exit(): exit so existe no console interativo


def main():
    args = ler_argumentos()
    sock, config_sessao = enviar_handshake(args.modo, args.envio, args.texto)
    print ("Configuração da sessão:", config_sessao)

    if args.mensagem is not None:
        # confere de novo com o valor confirmado no HSACK, que e o que vale para a sessao
        if len(args.mensagem) > config_sessao["tamanho_max_texto"]:
            encerrar_com_erro(sock, f"a mensagem passa do tamanho maximo confirmado pelo servidor ({config_sessao['tamanho_max_texto']}).")
        enviar_mensagem(sock, args.mensagem)


    sock.close()




if __name__ == "__main__":
    main()
