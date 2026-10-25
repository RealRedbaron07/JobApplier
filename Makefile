# One-word commands for the job OS and the card sniper.
#   make help
PY ?= python3
SNIPE := $(PY) snipe.py

.DEFAULT_GOAL := help
.PHONY: help setup test jobs dash login snipe live scan deals bids list value collection add rm cancel

help: ## show this list
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "  add example: make add NAME=\"Moonbreon\" CARD=\"Umbreon VMAX (Alternate Art Secret)\" SET=\"Evolving Skies\" NUM=215/203 KW=\"umbreon vmax 'alt art|215/203'\" REGRADE=1"

setup: ## install dependencies
	$(PY) -m pip install -r requirements.txt

test: ## run the test suite
	$(PY) -m pytest -q

dash: ## start the dashboard: jobs at http://127.0.0.1:5000, cards at /snipe
	$(PY) run.py

jobs: dash ## alias for dash

login: ## sign in to eBay + Facebook once (saved in the sniper Chrome profile)
	$(SNIPE) login

snipe: ## watch for deals (dry-run: alerts only, bids/messages simulated)
	$(SNIPE) watch

live: ## watch for deals and REALLY snipe auctions / message sellers
	$(SNIPE) --live watch

scan: ## one dry-run pass
	$(SNIPE) scan

deals: ## recent matched deals
	$(SNIPE) deals

bids: ## scheduled / finished snipes
	$(SNIPE) bids

list: ## show the watchlist
	$(SNIPE) list

value: ## market values per grade (TCGPlayer / PriceCharting / eBay sold); REFRESH=1 to refetch
	$(SNIPE) value $(if $(NAME),"$(NAME)") $(if $(REFRESH),--refresh)

collection: ## sync + show your Collectr showcase (COLLECTR_SHOWCASE_URL)
	$(SNIPE) collection

add: ## add a target: NAME= CARD= SET= NUM= [MAX=] [MIN=] [BID=] [KW="..."] [REGRADE=1] [GRADED=1] [BARGAIN=20]
	@test -n "$(NAME)" || (echo 'usage: make add NAME="Moonbreon" CARD="Umbreon VMAX (Alternate Art Secret)" SET="Evolving Skies" NUM=215/203 [MAX=550] [BID=600] [KW="a b \"c|d\""] [REGRADE=1]'; exit 1)
	$(SNIPE) add "$(NAME)" $(if $(CARD),--card "$(CARD)") $(if $(SET),--set "$(SET)") $(if $(NUM),--number "$(NUM)") \
		$(if $(MAX),--max $(MAX)) $(if $(MIN),--min $(MIN)) $(if $(BID),--max-bid $(BID)) $(if $(BARGAIN),--bargain $(BARGAIN)) \
		$(if $(KW),--keywords $(KW)) $(if $(REGRADE),--regrade) $(if $(GRADED),--graded-only)

rm: ## remove a target: NAME=
	$(SNIPE) remove "$(NAME)"

cancel: ## cancel a pending snipe: ID=
	$(SNIPE) cancel-bid $(ID)
