@echo off
echo Running the daily News scraper script...
cd /d "C:\Users\kyleq\OneDrive\Documents\StockSentiment\scrapers"
python news_scraper.py >> "C:\Users\kyleq\OneDrive\Documents\StockSentiment\logs\news_log.txt" 2>&1