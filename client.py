#criar cabeçalho + handshake

# O cliente funciona em duas etapas, e a config_sessao liga uma na outra:
#
# 1. Handshake: o cliente propoe os parametros (vindos da linha de comando) e o servidor responde
#    com o HSACK. O enviar_handshake devolve a config_sessao, um dicionario com o que o servidor CONFIRMOU:
#        {"modo_retransmissao": "GBN", "tipo_envio": "LOTE", "tamanho_max_texto": 30, "tamanho_janela": 5}
#
# 2. Envio: daqui pra frente tudo e decidido pela config_sessao, e nao pelos argumentos digitados:
#    o tamanho maximo da mensagem, se o envio e GBN ou individual e o tamanho da janela.
#
# CP3: todo pacote que o cliente manda (HS e dados) passa pelo canal simulado (protocol.simular_canal),
# que pode perder ou corromper o pacote. Quais pacotes falham e escolhido na linha de comando
# (--perder / --corromper); sem essas opcoes o canal e limpo.

import argparse
import socket
import sys
import time
import config  # o simular_canal le config.SEQS_PERDIDOS / SEQS_CORROMPIDOS em tempo de execucao
from config import *
from protocol import montar_handshake_request, parsear_handshake, parsear_pacote, calcular_checksum_pacote
from protocol import montar_pacotes_mensagem, cifrar_mensagem, simular_canal


# Todo pacote do cliente sai por aqui, passando antes pelo canal simulado.
# O canal pode devolver o pacote normal, estragado ou None (perdido).
def enviar(sock, pacote):
    resultado = simular_canal(pacote)

    # perdido: simplesmente nao envia. O cliente vai perceber pelo timer, como na rede de verdade
    if resultado is None:
        print(f"[SIMULACAO] PERDIDO, nao enviado: {pacote!r}")
        return

    if resultado != pacote:
        print(f"[SIMULACAO] CORROMPIDO: {pacote!r} -> {resultado!r}")

    sock.sendto(resultado.encode(ENCODING), (HOST, PORTA))
    print("Pacote enviado:", repr(resultado))

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
        enviar(sock, handshake) # envia o handshake para o servidor (passa pelo canal simulado: --perder 0 / --corromper 0 afetam o HS)
        tentativas += 1
        resposta = receber_resposta(sock, [TYPE_HANDSHAKE_ACK], [0]) # so aceita um HSACK valido vindo do servidor
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

# Converte os argumentos que chegam em uma lista pra informar o canal simulado quais pacotes devem ser perdidos ou corrompidos. Ex.: "1,3" vira [1, 3]. São os que vem do --perder e --corromper. Se vierem caracteres que não são números, ou números negativos, dispara um erro de argumento.
def lista_de_seqs(texto):
    try:
        seqs = [int(parte) for parte in texto.split(",") if parte.strip() != ""]
    except ValueError:
        raise argparse.ArgumentTypeError(f"use numeros separados por virgula, ex.: 1,3 (recebido {texto!r})")
    if any(seq < 0 for seq in seqs):
        raise argparse.ArgumentTypeError("seq nao pode ser negativo")
    return seqs


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
    # simulacao de falhas (CP3): erro deterministico, definido no cliente e verificado pelo servidor.
    # Cada seq listado falha so na 1a tentativa; a retransmissao passa. O seq 0 vale tambem para o HS.
    parser.add_argument("--perder", type=lista_de_seqs, default=[], metavar="SEQS",
                        help="seqs que se perdem na 1a tentativa, separados por virgula (ex.: 1,3)")
    parser.add_argument("--corromper", type=lista_de_seqs, default=[], metavar="SEQS",
                        help="seqs que chegam corrompidos na 1a tentativa, separados por virgula (ex.: 2)")
    
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


# Retorno:
#   a string do pacote, se chegar uma resposta valida e esperada dentro do prazo;
#   None, se o prazo acabar (quem chamou trata como "sem resposta" e reenvia).
def receber_resposta(sock, tipos_esperados, seqs_esperados, espera=TIMEOUT_ENVIO):
   
    servidor = (socket.gethostbyname(HOST), PORTA)
    prazo = time.monotonic() + espera # monotonic: relogio que so anda pra frente (nao muda se o relogio do PC for ajustado)

    while True: # cada volta trata UM datagrama que chegou (ou o fim do prazo)
        
        restante = prazo - time.monotonic()
        if restante <= 0:
            return None
        sock.settimeout(restante) # o recvfrom so pode bloquear pelo tempo que sobrou



        try:
            dados, endereco = sock.recvfrom(TAM_RECV) # bloqueia ate chegar um datagrama ou o tempo acabar
        except (socket.timeout, ConnectionResetError):
            return None
        except OSError as erro:
            print(f"Descartado: datagrama invalido ({erro})")
            continue


        if endereco != servidor:
            print(f"Descartado: pacote de {endereco}, que nao e o servidor")
            continue


        # Falha se os bytes nao forem UTF-8 valido
        try:
            bruto = dados.decode(ENCODING)
            pacote = parsear_pacote(bruto) # {"tipo", "seq", "checksum", "payload"}
        except (UnicodeDecodeError, ValueError) as erro:
            print(f"Descartado: pacote malformado ({erro})")
            continue


        # ve se o pacote é valido calculando o checksum  
        valido = calcular_checksum_pacote(pacote) == pacote["checksum"]
        print(f"Recebido do servidor: tipo={pacote['tipo']} | seq={pacote['seq']} | "
              f"checksum={pacote['checksum']} | valido={valido}")

        if not valido:
            print("Descartado: checksum invalido:", repr(bruto))
            continue

        
        # descarta pacotes dos tipos que nao estao predefinidos
        if pacote["tipo"] not in tipos_esperados or pacote["seq"] not in seqs_esperados:
            print("Descartado: nao e o esperado:", bruto)
            continue

        # passou em todos os filtros: e a resposta que o chamador quer. Ele decide o que fazer
        # olhando o tipo (ACK -> anda / NACK -> reenvia imediatamente).
        return bruto


# Envio individual (pare e espere): manda um pacote e so passa para o proximo depois do ACK dele.
def enviar_individual(sock, mensagem):
    pacotes = montar_pacotes_mensagem(mensagem) # pedacos de 4 caracteres + MSGFIM no final
    print("Pacotes da mensagem:", pacotes)

    seq = 0         # pacote da vez (a posicao na lista e o proprio seq)
    tentativas = 0  # quantas vezes o timer do pacote da vez estourou

    while seq < len(pacotes):
        enviar(sock, pacotes[seq])
        resposta = receber_resposta(sock, [TYPE_DATA_ACK, TYPE_NACK], [seq])

        if resposta is None:
            # timer estourou: o pacote ou o ACK se perdeu. O laco reenvia o mesmo pacote
            tentativas = contar_tentativa(sock, tentativas, seq)
            print(f"Tentativa {tentativas}: sem ACK do seq={seq}, reenviando...")

        elif parsear_pacote(resposta)["tipo"] == TYPE_NACK:
            # chegou estragado no servidor: o laco reenvia o mesmo pacote, sem esperar o timer
            print(f"NACK do seq={seq}, reenviando imediatamente...")

        else:
            # ACK: esse pacote chegou certo, vamos para o proximo
            print(f"ACK do seq={seq} recebido")
            seq += 1
            tentativas = 0


# Go-Back-N: manda ate "janela" pacotes de uma vez, sem esperar ACK de cada um.
# O ACK e cumulativo (ACK 4 = "recebi tudo ate o 4") e existe um timer so.
# Se der problema, volta para o primeiro pacote sem ACK e reenvia tudo a partir dele.
def enviar_gbn(sock, mensagem, janela):
    pacotes = montar_pacotes_mensagem(mensagem) # pedacos de 4 caracteres + MSGFIM no final
    print("Pacotes da mensagem:", pacotes)

    base = 0        # primeiro pacote que ainda nao teve ACK (inicio da janela)
    proximo = 0     # proximo pacote que ainda nao foi enviado
    tentativas = 0  # quantas vezes o timer estourou sem a base andar

    while base < len(pacotes):
        # enche a janela: manda tudo que cabe entre a base e base + janela
        while proximo < len(pacotes) and proximo < base + janela:
            enviar(sock, pacotes[proximo])
            proximo += 1

        resposta = receber_resposta(sock, [TYPE_DATA_ACK, TYPE_NACK], range(base, proximo))

        if resposta is None:
            # timer estourou: volta para a base, e o laco de cima reenvia a janela inteira
            tentativas = contar_tentativa(sock, tentativas, base)
            print(f"Tentativa {tentativas}: sem ACK do seq={base}, reenviando a partir dele...")
            proximo = base
            continue

        pacote = parsear_pacote(resposta)
        janela = janela_do_servidor(pacote, janela) # o servidor pode ter mudado a janela

        if pacote["tipo"] == TYPE_NACK:
            # o NACK traz o seq que o servidor esta esperando, entao tudo antes dele ja chegou.
            # Volta para esse seq e reenvia a partir dele imediatamente, sem esperar o timer
            print(f"NACK do seq={pacote['seq']}, reenviando a partir dele imediatamente...")
            base = pacote["seq"]
            proximo = base

        else:
            # ACK cumulativo: tudo ate esse seq foi confirmado, entao a janela anda
            print(f"ACK do seq={pacote['seq']} recebido")
            base = pacote["seq"] + 1
            tentativas = 0


# Repeticao Seletiva: tambem manda ate "janela" pacotes de uma vez, mas:
# - o ACK e individual (ACK 4 = "recebi o 4", so ele);
# - cada pacote tem o seu proprio timer;
# - se der problema, reenvia so o pacote que falhou.
def enviar_sr(sock, mensagem, janela):
    pacotes = montar_pacotes_mensagem(mensagem) # pedacos de 4 caracteres + MSGFIM no final
    print("Pacotes da mensagem:", pacotes)

    base = 0             # primeiro pacote que ainda nao teve ACK (inicio da janela)
    proximo = 0          # proximo pacote que ainda nao foi enviado
    confirmados = set()  # pacotes que ja tiveram ACK (podem chegar fora de ordem)
    hora_envio = {}      # seq -> quando foi enviado pela ultima vez (e o timer de cada pacote)
    tentativas = {}      # seq -> quantas vezes o timer daquele pacote estourou

    while base < len(pacotes):
        # enche a janela e liga o timer de cada pacote enviado
        while proximo < len(pacotes) and proximo < base + janela:
            enviar(sock, pacotes[proximo])
            hora_envio[proximo] = time.monotonic()
            tentativas[proximo] = 0
            proximo += 1

        # pendentes: ja enviados e ainda sem ACK.
        # Espera so ate o timer mais antigo entre eles estourar
        pendentes = [seq for seq in range(base, proximo) if seq not in confirmados]
        mais_antigo = min(hora_envio[seq] for seq in pendentes)
        espera = mais_antigo + TIMEOUT_ENVIO - time.monotonic()

        resposta = receber_resposta(sock, [TYPE_DATA_ACK, TYPE_NACK], pendentes, espera)

        if resposta is not None:
            pacote = parsear_pacote(resposta)
            seq = pacote["seq"]
            janela = janela_do_servidor(pacote, janela) # o servidor pode ter mudado a janela

            if pacote["tipo"] == TYPE_NACK:
                # chegou estragado: reenvia so esse pacote imediatamente e reinicia o timer dele
                print(f"NACK do seq={seq}, reenviando so ele imediatamente...")
                enviar(sock, pacotes[seq])
                hora_envio[seq] = time.monotonic()

            else:
                # ACK: marca so esse pacote. A janela anda enquanto o primeiro dela estiver confirmado
                print(f"ACK do seq={seq} recebido")
                confirmados.add(seq)
                while base in confirmados:
                    base += 1

        # confere os timers: reenvia so os pacotes cujo tempo acabou
        agora = time.monotonic()
        for seq in range(base, proximo):
            if seq not in confirmados and agora - hora_envio[seq] >= TIMEOUT_ENVIO:
                tentativas[seq] = contar_tentativa(sock, tentativas[seq], seq)
                print(f"Tentativa {tentativas[seq]}: sem ACK do seq={seq}, reenviando so ele...")
                enviar(sock, pacotes[seq])
                hora_envio[seq] = agora


# O servidor manda a janela atual no payload de cada ACK/NACK (ex.: MSGACK|3|cs|4).
# Se veio um valor valido e diferente, o cliente passa a usar a janela nova.
def janela_do_servidor(pacote, janela_atual):
    try:
        nova = int(pacote["payload"])
    except ValueError: # payload vazio ou estranho: mantem a janela que ja tinha
        return janela_atual
    if not JANELA_MIN <= nova <= JANELA_MAX:
        return janela_atual
    if nova != janela_atual:
        print(f"Janela: {janela_atual} -> {nova} (definida pelo servidor)")
    return nova


# Soma mais uma tentativa ao pacote. Se chegou no limite do config.py, o cliente desiste.
def contar_tentativa(sock, tentativas, seq):
    tentativas += 1
    if tentativas == MAX_TENTATIVAS_ENVIO:
        encerrar_com_erro(sock, f"o seq={seq} nao foi confirmado depois de {MAX_TENTATIVAS_ENVIO} tentativas.")
    return tentativas


def encerrar_com_erro(sock, motivo):
    print("Erro:", motivo)
    sock.close()
    sys.exit(1) # sys.exit em vez de exit(): exit so existe no console interativo


def main():
    args = ler_argumentos()

    # configura o canal simulado SO deste processo: o servidor importa o config.py separado,
    # entao continua com os valores do arquivo (canal limpo por padrao)
    config.SEQS_PERDIDOS = args.perder
    config.SEQS_CORROMPIDOS = args.corromper
    if args.perder or args.corromper:
        print(f"Canal com falhas: perder={args.perder} corromper={args.corromper} (so na 1a tentativa de cada seq)")
    else:
        print("Canal limpo (sem --perder / --corromper)")

    sock, config_sessao = enviar_handshake(args.modo, args.envio, args.texto)
    print ("Configuração da sessão:", config_sessao)

    # a partir daqui o cliente segue a config_sessao (o que o servidor confirmou), e nao os args

    if args.mensagem is not None:
        # confere de novo com o valor confirmado no HSACK, que e o que vale para a sessao
        if len(args.mensagem) > config_sessao["tamanho_max_texto"]:
            encerrar_com_erro(sock, f"a mensagem passa do tamanho maximo confirmado pelo servidor ({config_sessao['tamanho_max_texto']}).")

        # cifra a mensagem INTEIRA antes de fragmentar: o RC4 e uma cifra de fluxo, entao o servidor
        # so decifra depois de remontar tudo em ordem (finalizar_mensagem no server.py).
        # O limite de tamanho acima vale para o texto original, que e o que o usuario digitou.
        cifrada = cifrar_mensagem(CHAVE_CRIPTOGRAFIA, args.mensagem)
        print("Mensagem cifrada (RC4):", repr(cifrada))

        if config_sessao["tipo_envio"] == MODO_INDIVIDUAL:
            enviar_individual(sock, cifrada)
        elif config_sessao["modo_retransmissao"] == GBN:
            enviar_gbn(sock, cifrada, config_sessao["tamanho_janela"])
        else:
            enviar_sr(sock, cifrada, config_sessao["tamanho_janela"])
        print("Mensagem enviada e confirmada pelo servidor.")


    sock.close()




if __name__ == "__main__":
    main()
