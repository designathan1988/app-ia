"""Which builder command performs each action frame (read from frames.json's own statement that its core verbs are
the labels of these commands)."""

FRAME_COMMANDS = {"existir": "element.insert", "remover": "element.delete", "mover": "element.moveTo",
                  "renomear": "element.rename", "estilo": "style.set", "texto": "text.set"}
