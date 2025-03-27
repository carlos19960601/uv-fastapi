app/dev:
	uv run fastapi dev

app/run:
	uv run fastapi run

docker/app/build:
	docker build -t fastapi-app .