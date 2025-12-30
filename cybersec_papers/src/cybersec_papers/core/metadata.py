"""
Metadata management for paper information
"""

import csv
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class MetadataManager:
    """Manages paper metadata storage and retrieval"""

    def __init__(self, base_dir: Path, conference: str):
        """
        Initialize metadata manager

        Args:
            base_dir: Base directory for data storage
            conference: Conference directory name (e.g., "IEEE_SP")
        """
        self.base_dir = base_dir
        self.conference = conference

    def get_year_dir(self, year: int) -> Path:
        """Get directory for a specific year"""
        return self.base_dir / self.conference / str(year)

    def save(
        self,
        papers: List[Dict[str, Any]],
        year: int,
        formats: List[str] = None,
    ) -> None:
        """
        Save paper metadata to files

        Args:
            papers: List of paper info dicts
            year: Conference year
            formats: List of formats to save ('csv', 'json', 'txt', 'all')
        """
        if formats is None:
            formats = ['csv']
        elif 'all' in formats:
            formats = ['csv', 'json', 'txt']

        year_dir = self.get_year_dir(year)
        year_dir.mkdir(parents=True, exist_ok=True)

        for fmt in formats:
            if fmt == 'csv':
                self._save_csv(papers, year_dir / 'metadata.csv')
            elif fmt == 'json':
                self._save_json(papers, year_dir / 'metadata.json')
            elif fmt == 'txt':
                self._save_txt(papers, year_dir / 'metadata.txt')

        logger.info(f"Metadata saved: {', '.join(formats)} format")

    def _save_csv(self, papers: List[Dict], path: Path) -> None:
        """Save papers to CSV file"""
        if not papers:
            return

        # Collect all possible fields
        fields = set()
        for paper in papers:
            fields.update(paper.keys())

        # Standard field order
        priority_fields = ['title', 'authors', 'pdf_url', 'doi', 'abstract', 'source']
        ordered_fields = [f for f in priority_fields if f in fields]
        ordered_fields.extend(sorted(f for f in fields if f not in priority_fields))

        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=ordered_fields, extrasaction='ignore')
            writer.writeheader()
            for paper in papers:
                writer.writerow(paper)

    def _save_json(self, papers: List[Dict], path: Path) -> None:
        """Save papers to JSON file"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)

    def _save_txt(self, papers: List[Dict], path: Path) -> None:
        """Save papers to TXT file"""
        with open(path, 'w', encoding='utf-8') as f:
            for i, paper in enumerate(papers, 1):
                f.write(f"[{i}] {paper.get('title', 'Unknown')}\n")
                if paper.get('authors'):
                    f.write(f"    Authors: {paper['authors']}\n")
                if paper.get('pdf_url'):
                    f.write(f"    PDF: {paper['pdf_url']}\n")
                if paper.get('doi'):
                    f.write(f"    DOI: {paper['doi']}\n")
                f.write("\n")

    def load(self, year: int) -> Optional[List[Dict]]:
        """
        Load metadata from file

        Args:
            year: Conference year

        Returns:
            List of paper info dicts, or None if not found
        """
        year_dir = self.get_year_dir(year)

        # Try JSON first (most complete)
        json_path = year_dir / 'metadata.json'
        if json_path.exists():
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)

        # Try CSV
        csv_path = year_dir / 'metadata.csv'
        if csv_path.exists():
            papers = []
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    papers.append(dict(row))
            return papers

        return None

    def get_downloaded_papers(self, year: int) -> List[str]:
        """
        Get list of already downloaded paper filenames

        Args:
            year: Conference year

        Returns:
            List of PDF filenames (without extension)
        """
        papers_dir = self.get_year_dir(year) / 'papers'
        if not papers_dir.exists():
            return []

        return [p.stem for p in papers_dir.glob('*.pdf')]
