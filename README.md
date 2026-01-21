TO START USE THESE COMMANDS:

docker compose up

docker exec parser_site python manage.py migrate

docker exec redash_server bin/run ./manage.py database create_tables
