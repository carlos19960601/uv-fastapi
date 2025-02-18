app/run:
	uv run fastapi dev

docker/app/build:
	docker build -t fastapi-app .