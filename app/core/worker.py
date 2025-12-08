from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from app.core.parser import AvitoParser
from app.core.log_manager import logger


class ParserWorker(QObject):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)
    requests_count = pyqtSignal(int, int)
    
    def __init__(self, keywords, ignore_keywords, max_pages, max_total_items,
            min_price, max_price, sort_type,
            search_all_regions, debug_mode=False,
            search_mode="full", forced_categories=None,
            filter_defects=False,
            skip_duplicates=False,
            allow_rewrite_duplicates=False,
            merge_with_table=None):
        super().__init__()
        self.keywords = keywords
        self.ignore_keywords = ignore_keywords
        self.max_pages = max_pages
        self.max_total_items = max_total_items
        self.min_price = min_price
        self.max_price = max_price
        self.sort_type = sort_type
        self.search_all_regions = search_all_regions
        self.debug_mode = debug_mode
        self.search_mode = search_mode
        self.forced_categories = forced_categories
        self.filter_defects = filter_defects
        self.skip_duplicates = skip_duplicates
        self.allow_rewrite_duplicates = allow_rewrite_duplicates
        self.merge_with_table = merge_with_table

        if self.search_mode == "primary":
            self.max_items_per_page = self.max_total_items
        else:
            self.max_items_per_page = None

        self.parser = None
        self._stop_requested = False
        
    def request_stop(self):
        self._stop_requested = True
        if self.parser:
            self.parser.request_stop()
            
    @pyqtSlot()
    def run(self):
        results = []
        try:
            with AvitoParser(debug_mode=self.debug_mode) as self.parser:
                self.parser.progress_value.connect(self.progress.emit)
                self.parser.update_requests_count.connect(self.requests_count.emit)

                results = self.parser.search_items(
                    self.keywords,
                    self.ignore_keywords,
                    max_pages=self.max_pages,
                    max_items_per_page=self.max_items_per_page,
                    max_total_items=self.max_total_items,
                    min_price=self.min_price,
                    max_price=self.max_price,
                    sort_type=self.sort_type,
                    search_all_regions=self.search_all_regions,
                    search_mode=self.search_mode,
                    forced_categories=self.forced_categories,
                    filter_defects=self.filter_defects,
                    skip_duplicates=self.skip_duplicates,
                    allow_rewrite_duplicates=self.allow_rewrite_duplicates,
                    merge_with_table=self.merge_with_table,
                )
        except Exception as e:
            print(f"PARSER WORKER ERROR: {e}")
            self.error.emit(str(e))
        finally:
            self.finished.emit(results if results else [])

class CategoryScannerWorker(QObject):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    
    def __init__(self, keywords):
        super().__init__()
        self.keywords = keywords
        
    @pyqtSlot()
    def run(self):
        parser = None
        try:
            with AvitoParser(debug_mode=True) as parser:
                categories = parser.get_dropdown_options(' '.join(self.keywords))
                self.finished.emit(categories)
        except Exception as e:
            self.error.emit(str(e))