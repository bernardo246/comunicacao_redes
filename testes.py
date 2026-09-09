import argparse
import signal
import socket
import subprocess
import sys
import time

import config
import protocol

PYTHON = sys.executable
LARGURA = 62


def executar_python(argumentos, timeout=45):
    processo = subprocess.run([PYTHON] + argumentos, capture_output=True, text=True, timeout=timeout)
    return (processo.stdout + processo.stderr).strip()


def enviar_bruto(pacote, esperar_resposta=True, timeout=2):
    if isinstance(pacote, str):
        pacote = pacote.encode(config.ENCODING)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(pacote, (config.HOST, config.PORTA))
        if not esperar_resposta:
            return "(enviado, sem esperar resposta)"
        dados, _ = sock.recvfrom(config.TAM_RECV)
        return dados.decode(config.ENCODING)
    except socket.timeout:
        return "SEM RESPOSTA (timeout)"
    finally:
        sock.close()


def capturar_erro(funcao):
    try:
        funcao()
    except Exception as erro:
        return f"{type(erro).__name__}: {erro}"
    return "nenhuma excecao levantada"


def porta_ocupada():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((config.HOST, config.PORTA))
        return False
    except OSError:
        return True
    finally:
        sock.close()


# ---------------------------------------------------------------- grupo A
def a1():
    saida = executar_python(["protocol.py"])
    ok = "HS|0|712|GBN,LOTE,50" in saida and "HSACK|0|809|GBN,LOTE,50,5" in saida
    return ok, saida, "HS|0|712|GBN,LOTE,50 e HSACK|0|809|GBN,LOTE,50,5 na saida"


def a2():
    obtido = protocol.calcular_checksum(config.CHECKSUM_ASCII, "ABC")
    return obtido == 198, str(obtido), "198"


def a3():
    obtido = protocol.calcular_checksum(config.CHECKSUM_ASCII, "")
    return obtido == 0, str(obtido), "0"


def a4():
    pacote = protocol.montar_pacote("HS", 7, 456, "GBN,LOTE,30")
    campos = protocol.parsear_pacote(pacote)
    esperado = {"tipo": "HS", "seq": 7, "checksum": 456, "payload": "GBN,LOTE,30"}
    ok = pacote == "HS|7|456|GBN,LOTE,30" and campos == esperado
    return ok, f"{pacote}\n{campos}", f"HS|7|456|GBN,LOTE,30\n{esperado}"


def a5():
    pacote = protocol.montar_pacote("DATA", 1, 0, "texto|com|barras")
    obtido = protocol.parsear_pacote(pacote)["payload"]
    return obtido == "texto|com|barras", obtido, "texto|com|barras"


def a6():
    pacote = protocol.montar_handshake_request(config.GBN, config.MODO_LOTE, 30)
    campos = protocol.parsear_handshake(pacote)
    esperado = {
        "tipo": config.TYPE_HANDSHAKE_REQ,
        "modo_retransmissao": "GBN",
        "tipo_envio": "LOTE",
        "tamanho_max_texto": 30,
    }
    ok = pacote == "HS|0|710|GBN,LOTE,30" and campos == esperado
    return ok, f"{pacote}\n{campos}", f"HS|0|710|GBN,LOTE,30\n{esperado}"


def a7():
    pacote = protocol.montar_handshake_ack(config.SR, config.MODO_INDIVIDUAL, 50, 3)
    campos = protocol.parsear_handshake(pacote)
    esperado = {
        "tipo": config.TYPE_HANDSHAKE_ACK,
        "modo_retransmissao": "SR",
        "tipo_envio": "IND",
        "tamanho_max_texto": 50,
        "tamanho_janela": 3,
    }
    ok = pacote == "HSACK|0|668|SR,IND,50,3" and campos == esperado
    return ok, f"{pacote}\n{campos}", f"HSACK|0|668|SR,IND,50,3\n{esperado}"


# ---------------------------------------------------------------- grupo B
def b1():
    saida = executar_python(["client.py"])
    ok = "'tamanho_janela': 5" in saida and "'tamanho_max_texto': 30" in saida
    return ok, saida, "HSACK com tamanho_max_texto 30 e tamanho_janela 5"


def b2():
    linhas = []
    for _ in range(3):
        saida = executar_python(["client.py"])
        linhas.append(saida.splitlines()[-1])
    ok = all("'tamanho_janela': 5" in linha for linha in linhas)
    return ok, "\n".join(linhas), "as tres execucoes recebem o mesmo HSACK"


def b3():
    saida = executar_python(["client.py", "--modo", "SR", "--envio", "IND", "--texto", "77"])
    ok = ("HS|0|582|SR,IND,77" in saida
          and "'modo_retransmissao': 'SR'" in saida
          and "'tipo_envio': 'IND'" in saida
          and "'tamanho_max_texto': 77" in saida)
    return ok, saida, "HS|0|582|SR,IND,77 e HSACK confirmando SR, IND e 77"


def b5():
    saida_texto = executar_python(["client.py", "--texto", "5"])
    saida_modo = executar_python(["client.py", "--modo", "XPTO"])
    ok = ("--texto deve ser no minimo 30" in saida_texto
          and "invalid choice" in saida_modo)
    resumo = f"{saida_texto.splitlines()[-1]}\n{saida_modo.splitlines()[-1]}"
    return ok, resumo, "os dois sao barrados pelo cliente, sem chegar na rede"


def b4():
    saida = executar_python(["client.py"], timeout=60)
    ok = "número máximo de tentativas de handshake excedido" in saida
    return ok, saida, "5 tentativas de retransmissao e depois a mensagem de erro"


# ---------------------------------------------------------------- grupo C
def c1():
    obtido = enviar_bruto(protocol.montar_handshake_request(config.GBN, config.MODO_LOTE, 5))
    return obtido == "HSACK|0|807|GBN,LOTE,30,5", obtido, "HSACK|0|807|GBN,LOTE,30,5"


def c2():
    modo = enviar_bruto(protocol.montar_handshake_request("XPTO", config.MODO_LOTE, 30))
    envio = enviar_bruto(protocol.montar_handshake_request(config.GBN, "ZZZ", 30))
    ok = modo.startswith("SEM RESPOSTA") and envio.startswith("SEM RESPOSTA")
    return ok, f"modo invalido  -> {modo}\nenvio invalido -> {envio}", "os dois sem resposta"


def c3():
    obtido = enviar_bruto(protocol.montar_pacote(config.TYPE_HANDSHAKE_ACK, 0, 0, "GBN,LOTE,30,5"))
    return obtido.startswith("SEM RESPOSTA"), obtido, "SEM RESPOSTA (timeout)"


def c4():
    enviar_bruto(b"LIXO", esperar_resposta=False)
    enviar_bruto(bytes([0xFF, 0xFE]), esperar_resposta=False)
    time.sleep(0.3)
    depois = enviar_bruto(protocol.montar_handshake_request(config.GBN, config.MODO_LOTE, 30))
    ok = depois == "HSACK|0|807|GBN,LOTE,30,5"
    return ok, f"apos o lixo o servidor respondeu: {depois}", "HSACK|0|807|GBN,LOTE,30,5"


def c5():
    obtido = enviar_bruto(protocol.montar_pacote(config.TYPE_HANDSHAKE_REQ, 0, 1, "GBN,LOTE,30"))
    ok = obtido == "HSACK|0|807|GBN,LOTE,30,5"
    return ok, obtido, "HSACK|0|807|GBN,LOTE,30,5 (checksum ainda nao e conferido)"


# ---------------------------------------------------------------- grupo D
def d1():
    obtido = capturar_erro(lambda: protocol.parsear_pacote("HS|0|123"))
    return obtido.startswith("ValueError: not enough values to unpack"), obtido, "ValueError: not enough values to unpack (expected 4, got 3)"


def d2():
    obtido = capturar_erro(lambda: protocol.parsear_pacote("HS|abc|123|GBN,LOTE,30"))
    return obtido.startswith("ValueError: invalid literal for int()"), obtido, "ValueError: invalid literal for int() with base 10: 'abc'"


def d3():
    obtido = capturar_erro(lambda: protocol.parsear_handshake("HSACK|0|0|GBN,LOTE,30"))
    return obtido.startswith("IndexError"), obtido, "IndexError: list index out of range"


def d4():
    obtido = capturar_erro(lambda: protocol.parsear_handshake("HS|0|0|GBN"))
    return obtido.startswith("IndexError"), obtido, "IndexError: list index out of range"


def d5():
    obtido = capturar_erro(lambda: protocol.calcular_checksum("CRC32", "ABC"))
    return obtido.startswith("ValueError: Algoritmo de checksum"), obtido, "ValueError: Algoritmo de checksum nao suportado"


TESTES = [
    ("A1", "auto-teste embutido do protocol.py", a1, False, False),
    ("A2", "checksum ASCII de 'ABC'", a2, False, False),
    ("A3", "checksum de payload vazio", a3, False, False),
    ("A4", "ida e volta de um pacote", a4, False, False),
    ("A5", "payload contendo o delimitador |", a5, False, False),
    ("A6", "handshake de pedido (HS)", a6, False, False),
    ("A7", "handshake de resposta (HSACK)", a7, False, False),
    ("B1", "handshake bem-sucedido pelo client.py", b1, True, False),
    ("B2", "varios clientes em sequencia", b2, True, False),
    ("B3", "cliente escolhendo SR, IND e 77", b3, True, False),
    ("B5", "parametros invalidos barrados no cliente", b5, False, False),
    ("B4", "cliente sem servidor no ar (lento, ~25s)", b4, False, True),
    ("C1", "tamanho abaixo do minimo corrigido para 30", c1, True, False),
    ("C2", "modo e tipo de envio invalidos recusados", c2, True, False),
    ("C3", "pacote de tipo inesperado descartado", c3, True, False),
    ("C4", "pacote lixo nao derruba o servidor", c4, True, False),
    ("C5", "checksum enviado mas ainda nao conferido", c5, True, False),
    ("D1", "faltam campos no pacote", d1, False, False),
    ("D2", "seq nao numerico", d2, False, False),
    ("D3", "HSACK sem a janela", d3, False, False),
    ("D4", "payload de handshake incompleto", d4, False, False),
    ("D5", "algoritmo de checksum inexistente", d5, False, False),
]

TITULOS = {
    "A": "GRUPO A - protocolo isolado (sem rede)",
    "B": "GRUPO B - handshake completo pela rede",
    "C": "GRUPO C - validacao e robustez do servidor",
    "D": "GRUPO D - pacotes malformados (sem rede)",
}


def selecionar(alvos):
    if not alvos:
        return [teste for teste in TESTES if not teste[4]]

    escolhidos = []
    pedidos = [alvo.upper() for alvo in alvos]
    for teste in TESTES:
        if teste[0] in pedidos or teste[0][0] in pedidos:
            escolhidos.append(teste)
    return escolhidos


def imprimir_bloco(texto, prefixo="        "):
    for linha in str(texto).splitlines():
        print(prefixo + linha)


def main():
    parser = argparse.ArgumentParser(description="Bateria de testes do trabalho de redes.")
    parser.add_argument("alvos", nargs="*", help="grupo (A, B, C, D) ou teste (A1, C4...). Sem argumento roda todos.")
    parser.add_argument("--completo", action="store_true", help="inclui tambem os testes lentos (B4)")
    parser.add_argument("--silencioso", action="store_true", help="mostra so o veredito de cada teste")
    args = parser.parse_args()

    escolhidos = selecionar(args.alvos)
    if args.completo:
        escolhidos = [teste for teste in TESTES if teste in escolhidos or teste[4]]
    if not escolhidos:
        print("Nenhum teste corresponde a", " ".join(args.alvos))
        return 2

    precisa_servidor = any(teste[3] for teste in escolhidos)
    tem_b4 = any(teste[0] == "B4" for teste in escolhidos)
    servidor = None
    servidor_externo = False

    if precisa_servidor or tem_b4:
        if porta_ocupada():
            servidor_externo = True
            print(f"Ja existe algo escutando em {config.HOST}:{config.PORTA}; usando esse servidor.")
        elif precisa_servidor:
            servidor = subprocess.Popen(
                [PYTHON, "-u", "server.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            time.sleep(1)
            print(f"Servidor iniciado pelo script em {config.HOST}:{config.PORTA}.")

    passaram = 0
    falharam = 0
    pulados = []
    grupo_atual = None

    try:
        for identificador, titulo, funcao, usa_servidor, lento in escolhidos:
            grupo = identificador[0]
            if grupo != grupo_atual:
                grupo_atual = grupo
                print()
                print("=" * LARGURA)
                print(TITULOS[grupo])
                print("=" * LARGURA)

            if identificador == "B4":
                if servidor_externo:
                    pulados.append((identificador, "servidor externo no ar; feche-o para rodar o B4"))
                    print(f"{identificador}  {titulo:<48} [PULADO]")
                    continue
                if servidor is not None:
                    servidor.send_signal(signal.SIGINT)
                    servidor.wait(timeout=5)

            try:
                ok, obtido, esperado = funcao()
            except Exception as erro:
                ok, obtido, esperado = False, f"{type(erro).__name__}: {erro}", "sem excecao"

            print(f"{identificador}  {titulo:<48} {'[OK]' if ok else '[FALHOU]'}")
            if not args.silencioso:
                imprimir_bloco(obtido)
            if not ok:
                print("        --- esperado ---")
                imprimir_bloco(esperado)

            if ok:
                passaram += 1
            else:
                falharam += 1

            if identificador == "B4" and servidor is not None:
                servidor = subprocess.Popen(
                    [PYTHON, "-u", "server.py"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                time.sleep(1)
    finally:
        log = ""
        if servidor is not None and servidor.poll() is None:
            servidor.send_signal(signal.SIGINT)
            try:
                log = servidor.communicate(timeout=5)[0]
            except subprocess.TimeoutExpired:
                servidor.kill()
                log = servidor.communicate()[0]

        if log.strip():
            print()
            print("=" * LARGURA)
            print("LOG DO SERVIDOR")
            print("=" * LARGURA)
            print(log.strip())

    print()
    print("=" * LARGURA)
    print(f"RESUMO: {passaram} OK, {falharam} falharam, {len(pulados)} pulados")
    for identificador, motivo in pulados:
        print(f"  {identificador} pulado: {motivo}")
    print("=" * LARGURA)
    return 1 if falharam else 0


if __name__ == "__main__":
    sys.exit(main())
