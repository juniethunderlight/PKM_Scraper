# PKMN — Gestor de Pokédex para TTRPG

Herramienta de línea de comandos para gestionar fichas de Pokémon en Google Sheets, orientada a campañas de TTRPG.
Esta app hace un scrapping de Wikidex para crear pokémon.

## Requisitos

```bash
pip install -r requirements.txt
```

Necesitas un archivo `credentials.json` con credenciales de una cuenta de servicio de Google con acceso a la hoja de cálculo.

## Uso

```bash
python pkmn.py addmove   <nombre_movimiento>      # Agrega un movimiento a la hoja
python pkmn.py addpkm    <nombre_pokemon> [nivel] # Agrega un Pokémon nuevo
python pkmn.py updatepkm <nombre_pokemon> [nivel] # Actualiza la ficha de un Pokémon
python pkmn.py hidepkm   <nombre_pokemon>         # Oculta la pestaña del Pokémon
python pkmn.py showpkm   <nombre_pokemon>         # Muestra la pestaña del Pokémon
python pkmn.py orderby                            # Ordena la hoja por criterio
```

## Archivos

| Archivo | Descripción |
| --- | --- |
| `pkmn.py` | Script principal (CLI) |
| `scraper.py` | Obtiene datos de Pokémon desde la web |
| `gui.py` | Interfaz gráfica (alternativa al CLI) |
| `credentials.json` | Credenciales de Google (no incluir en git) |
