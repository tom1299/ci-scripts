import json
import rel
import websocket


def on_message(ws, message):
    for stream in json.loads(message)["streams"]:
        print(json.dumps(stream, indent=4))


def on_error(ws, error):
    print(error)


if __name__ == "__main__":
    header = {'Sec-WebSocket-Key: dGVzdC13ZWJzb2NrZXQK', 'Sec-WebSocket-Version: 13',
              'Sec-WebSocket-Extensions: permessage-deflate', 'Connection: keep-alive, Upgrade', 'Upgrade: websocket'}

    ws = websocket.WebSocketApp('ws://localhost:3100/loki/api/v1/tail?query={cluster="wlan-1.refsa1.bn"}',
                                on_message=on_message, on_error=on_error, header=header)

    ws.run_forever(dispatcher=rel, http_proxy_host="localhost", http_proxy_port=1337, proxy_type="socks5")
    rel.signal(2, rel.abort)  # Keyboard Interrupt
    rel.dispatch()
