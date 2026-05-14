.PHONY: help build up down start stop restart logs db-shell app-shell run clean rebuild ps db-reset

help:           ## Показать список целей
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-12s %s\n", $$1, $$2}'

build:          ## Собрать образы
	docker compose build

up:             ## Запустить БД и приложение (фоном)
	@xhost +local:root >/dev/null 2>&1 || true
	docker compose up -d

start: up       ## Алиас для up

run:            ## Запустить приложение в foreground (для интерактивного GUI)
	@xhost +local:root >/dev/null 2>&1 || true
	docker compose up --build

down:           ## Остановить и удалить контейнеры (volume сохраняется)
	docker compose down

stop: down      ## Алиас для down

restart:        ## Перезапустить контейнеры
	docker compose restart

logs:           ## Хвост логов
	docker compose logs -f --tail=200

ps:             ## Статус контейнеров
	docker compose ps

db-shell:       ## psql в контейнере БД
	docker compose exec db psql -U postgres -d dietplan

app-shell:      ## bash в контейнере приложения
	docker compose exec app bash

clean:          ## Удалить контейнеры и том БД (данные потеряются!)
	docker compose down -v

db-reset:       ## Перезалить БД из sql/01_schema.sql + 02_seed.sql (без пересборки образа)
	docker compose exec -T db psql -U postgres -d dietplan -f /docker-entrypoint-initdb.d/01_schema.sql
	docker compose exec -T db psql -U postgres -d dietplan -f /docker-entrypoint-initdb.d/02_seed.sql
	@echo "БД сброшена к начальному состоянию."

rebuild: clean build up   ## Полная пересборка с нуля
