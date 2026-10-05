.DEFAULT_GOAL := all
.PHONY: all
all: app

generated.h: value.txt generate.py
	@printf 'generate\n' >> recipes.log
	@"$(PYTHON)" generate.py

# Both inputs affect app's content, so both are normal prerequisites.
app: main.c generated.h
	@printf 'compile\n' >> recipes.log
	@"$(CC)" -std=c11 -Wall -Wextra -Werror -O0 main.c -o app
