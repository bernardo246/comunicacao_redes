#criar cabeçalho + handshake

# O cliente funciona em duas etapas, e a config_sessao liga uma na outra:
#
# 1. Handshake: o cliente propoe os parametros (vindos da linha de comando) e o servidor responde
#    com o HSACK. O enviar_handshake devolve a config_sessao, um dicionario com o que o servidor CONFIRMOU:
#        {"modo_retransmissao": "GBN", "tipo_envio": "LOTE", "tamanho_max_texto": 30, "tamanho_janela": 5}
#
# 2. Envio: daqui pra frente tudo e decidido pela config_sessao, e nao pelos argumentos digitados:
#    o tamanho maximo da mensagem, se o envio e GBN ou individual e o tamanho da janela.

import argparse
import socket
import sys
import time
from config import *
from protocol import montar_handshake_request, parsear_handshake, parsear_pacote, calcular_checksum_pacote
from protocol import montar_pacotes_mensagem

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
        resposta = receber_resposta(sock, TYPE_HANDSHAKE_ACK, [0]) # so aceita um HSACK valido vindo do servidor
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


# espera um pacote do tipo esperado com o seq dentro de seqs_esperados (ex.: [0] ou range(2, 5)).
# espera: quantos segundos esperar (por padrao TIMEOUT_ENVIO).
# Retorna o pacote (string) ou None se o prazo acabar.
# Qualquer outra coisa que chegar no meio do caminho e descartada, sem derrubar o cliente.
def receber_resposta(sock, tipo_esperado, seqs_esperados, espera=TIMEOUT_ENVIO):
    servidor = (socket.gethostbyname(HOST), PORTA) # recvfrom devolve o IP, entao compara com o IP do HOST
    prazo = time.monotonic() + espera # prazo fixo: pacotes errados chegando nao renovam o tempo de espera

    while True:
        restante = prazo - time.monotonic()
        if restante <= 0:
            return None
        sock.settimeout(restante)
        # recebendo os dados
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

        if calcular_checksum_pacote(pacote) != pacote["checksum"]:
            print("Descartado: checksum invalido:", bruto)
            continue

        if pacote["tipo"] != tipo_esperado or pacote["seq"] not in seqs_esperados:
            print("Descartado: nao e o esperado:", bruto) # ex.: ACK repetido de um pacote anterior
            continue

        return bruto


def enviar_individual(sock, mensagem):
    pacotes = montar_pacotes_mensagem(mensagem) # pedacos de 4 caracteres e o MSGFIM no final
    print("Pacotes da mensagem:", pacotes)

    indice = 0 # posicao do pacote atual na lista, e tambem o seq dele
    tentativas = 0
    while indice < len(pacotes): # so passa para o proximo pacote quando o atual for confirmado
        pacote = pacotes[indice]
        sock.sendto(pacote.encode(ENCODING), (HOST, PORTA)) # mesmo socket do handshake, para o servidor achar a sessao
        print("Pacote enviado:", pacote)

        if receber_resposta(sock, TYPE_DATA_ACK, [indice]) is not None:
            print(f"ACK do seq={indice} recebido")
            indice += 1
            tentativas = 0 # zera para o proximo pacote
        else:
            tentativas += 1
            if tentativas == MAX_TENTATIVAS_ENVIO:
                encerrar_com_erro(sock, f"o seq={indice} nao foi confirmado depois de {MAX_TENTATIVAS_ENVIO} tentativas.")
            print(f"Tentativa {tentativas}: sem ACK do seq={indice}, reenviando...")


# Go-Back-N: manda varios pacotes de uma vez, ate o tamanho da janela.
# O ACK e cumulativo: o ACK do seq n confirma todos os pacotes ate n.
# Se o tempo acabar sem ACK, volta para o primeiro pacote sem confirmacao e reenvia a partir dele.
def enviar_gbn(sock, mensagem, janela):
    pacotes = montar_pacotes_mensagem(mensagem) # pedacos de 4 caracteres e o MSGFIM no final
    print("Pacotes da mensagem:", pacotes)

    base = 0      # primeiro pacote que ainda nao foi confirmado
    proximo = 0   # proximo pacote que ainda nao foi enviado
    tentativas = 0

    while base < len(pacotes):
        # manda todos os pacotes que cabem na janela
        while proximo < len(pacotes) and proximo < base + janela:
            sock.sendto(pacotes[proximo].encode(ENCODING), (HOST, PORTA))
            print("Pacote enviado:", pacotes[proximo])
            proximo += 1

        # aceita o ACK de qualquer pacote que ja foi enviado e ainda nao foi confirmado
        resposta = receber_resposta(sock, TYPE_DATA_ACK, range(base, proximo))

        if resposta is not None:
            seq_confirmado = parsear_pacote(resposta)["seq"]
            print(f"ACK do seq={seq_confirmado} recebido")
            base = seq_confirmado + 1 # tudo ate esse seq foi confirmado, entao a janela anda
            tentativas = 0
        else:
            tentativas += 1
            if tentativas == MAX_TENTATIVAS_ENVIO:
                encerrar_com_erro(sock, f"o seq={base} nao foi confirmado depois de {MAX_TENTATIVAS_ENVIO} tentativas.")
            print(f"Tentativa {tentativas}: sem ACK do seq={base}, reenviando a partir dele...")
            proximo = base # volta para a base, e o laco de cima reenvia a janela


# Repeticao Seletiva: manda varios pacotes de uma vez, ate o tamanho da janela, igual ao GBN.
# A diferenca: o ACK e individual (o ACK do seq n confirma so o n) e cada pacote tem o seu proprio timer.
# Se o tempo de um pacote acabar sem ACK, reenvia so ele.
# a janela so anda quando o primeiro chegar
def enviar_sr(sock, mensagem, janela):
    pacotes = montar_pacotes_mensagem(mensagem) # pedacos de 4 caracteres e o MSGFIM no final
    print("Pacotes da mensagem:", pacotes)

    base = 0         # primeiro pacote que ainda nao foi confirmado
    proximo = 0      # proximo pacote que ainda nao foi enviado
    confirmados = [] # seqs que ja receberam ACK, mesmo fora de ordem
    hora_envio = {}  # seq -> hora do ultimo envio daquele pacote (e o timer dele) [Dicionario]
    tentativas = {}  # seq -> quantas vezes o tempo daquele pacote acabou

    while base < len(pacotes):
        # manda todos os pacotes que cabem na janela
        while proximo < len(pacotes) and proximo < base + janela:
            sock.sendto(pacotes[proximo].encode(ENCODING), (HOST, PORTA))
            print("Pacote enviado:", pacotes[proximo])
            hora_envio[proximo] = time.monotonic()
            tentativas[proximo] = 0
            proximo += 1

        # pacotes que ja foram enviados e ainda esperam ACK
        pendentes = []
        for seq in range(base, proximo):
            if seq not in confirmados: # isso tem que ser feito porque o ACK pode chegar fora de ordem, e a janela anda so quando o primeiro pacote dela for confirmado
                pendentes.append(seq)

        # espera so ate o timer do pacote mais antigo acabar
        mais_antigo = pendentes[0]
        for seq in pendentes:
            if hora_envio[seq] < hora_envio[mais_antigo]:
                mais_antigo = seq
        espera = hora_envio[mais_antigo] + TIMEOUT_ENVIO - time.monotonic()

        resposta = receber_resposta(sock, TYPE_DATA_ACK, pendentes, espera) # so aceita ACK de pacotes que ja foram enviados e ainda nao foram confirmados

        if resposta is not None:
            seq_confirmado = parsear_pacote(resposta)["seq"] 
            print(f"ACK do seq={seq_confirmado} recebido")
            confirmados.append(seq_confirmado)

            # a janela so anda quando o primeiro pacote dela for confirmado
            while base in confirmados:
                base += 1

        # reenvia so os pacotes cujo tempo acabou
        agora = time.monotonic()
        for seq in range(base, proximo):
            if seq in confirmados:
                continue
            if agora - hora_envio[seq] < TIMEOUT_ENVIO:
                continue

            tentativas[seq] += 1
            if tentativas[seq] == MAX_TENTATIVAS_ENVIO:
                encerrar_com_erro(sock, f"o seq={seq} nao foi confirmado depois de {MAX_TENTATIVAS_ENVIO} tentativas.")
            print(f"Tentativa {tentativas[seq]}: sem ACK do seq={seq}, reenviando so ele...")
            sock.sendto(pacotes[seq].encode(ENCODING), (HOST, PORTA))
            print("Pacote enviado:", pacotes[seq])
            hora_envio[seq] = agora # o timer recomeca so para este pacote


def encerrar_com_erro(sock, motivo):
    print("Erro:", motivo)
    sock.close()
    sys.exit(1) # sys.exit em vez de exit(): exit so existe no console interativo


def main():
    args = ler_argumentos()
    sock, config_sessao = enviar_handshake(args.modo, args.envio, args.texto)
    print ("Configuração da sessão:", config_sessao)

    # a partir daqui o cliente segue a config_sessao (o que o servidor confirmou), e nao os args

    if args.mensagem is not None:
        # confere de novo com o valor confirmado no HSACK, que e o que vale para a sessao
        if len(args.mensagem) > config_sessao["tamanho_max_texto"]:
            encerrar_com_erro(sock, f"a mensagem passa do tamanho maximo confirmado pelo servidor ({config_sessao['tamanho_max_texto']}).")

        if config_sessao["tipo_envio"] == MODO_INDIVIDUAL:
            enviar_individual(sock, args.mensagem)
        elif config_sessao["modo_retransmissao"] == GBN:
            enviar_gbn(sock, args.mensagem, config_sessao["tamanho_janela"])
        else:
            enviar_sr(sock, args.mensagem, config_sessao["tamanho_janela"])


    sock.close()




if __name__ == "__main__":
    main()
