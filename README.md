# kvalitaovzdusia.sk

Čistá inštalácia: statická stránka na GitHub Pages, doména `www.kvalitaovzdusia.sk`.

## Súbory
- `index.html` – úvodná stránka (zatiaľ „Stránka sa pripravuje")
- `CNAME` – vlastná doména pre GitHub Pages
- `.nojekyll` – vypína Jekyll, stránka sa publikuje tak, ako je
- `.gitignore` – súbory, ktoré sa nemajú nahrávať

## Publikovanie
1. Settings → Pages → Source: *Deploy from a branch* → Branch `main` / `/ (root)`.
2. Custom domain: `www.kvalitaovzdusia.sk`, potom *Enforce HTTPS*.
3. DNS u registrátora: `CNAME` záznam `www` → `lalasonycierny.github.io`.
