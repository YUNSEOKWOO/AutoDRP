import os
import glob
from typing import List, Dict, Any, Optional
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from datetime import datetime


class PDFAnalyzer:
    """Comprehensive PDF analysis and processing class."""
    
    def __init__(self, base_dir: str = "./models"):
        self.base_dir = base_dir
        self.embeddings = OpenAIEmbeddings()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", ".", " ", ""]
        )
    
    def find_pdf_files(self, base_dir: Optional[str] = None) -> List[str]:
        """Find all PDF files in the specified directory and subdirectories."""
        search_dir = base_dir or self.base_dir
        if not os.path.exists(search_dir):
            return []
        
        pdf_files = []
        for pattern in [f"{search_dir}/**/*.pdf", f"{search_dir}/*.pdf"]:
            pdf_files.extend(glob.glob(pattern, recursive=True))
        
        return sorted(pdf_files)
    
    def auto_find_pdf(self, pdf_identifier: Optional[str] = None, base_dir: Optional[str] = None) -> Optional[str]:
        """Automatically find a PDF file based on identifier or return the first available PDF."""
        pdf_files = self.find_pdf_files(base_dir)
        
        if not pdf_files:
            return None
        
        if not pdf_identifier:
            return pdf_files[0]
        
        # Try exact filename match first
        for pdf_path in pdf_files:
            if os.path.basename(pdf_path) == pdf_identifier:
                return pdf_path
        
        # Try partial filename match
        for pdf_path in pdf_files:
            if pdf_identifier.lower() in os.path.basename(pdf_path).lower():
                return pdf_path
        
        # Try path match
        for pdf_path in pdf_files:
            if pdf_identifier.lower() in pdf_path.lower():
                return pdf_path
        
        return None
    
    def normalize_pdf_path(self, pdf_path: str) -> str:
        """Normalize PDF path to handle both absolute and relative paths correctly."""
        if os.path.isabs(pdf_path):
            return pdf_path
        
        if pdf_path.startswith('./models/') or pdf_path.startswith('models/'):
            return pdf_path
        
        return os.path.join(self.base_dir, pdf_path)
    
    def extract_metadata(self, pdf_path: str) -> Dict[str, Any]:
        """Extract basic metadata from PDF."""
        try:
            loader = PyMuPDFLoader(pdf_path)
            docs = loader.load()
            
            metadata = {
                'file_path': pdf_path,
                'file_size': os.path.getsize(pdf_path),
                'num_pages': len(docs),
                'extraction_time': datetime.now().isoformat()
            }
            
            if docs:
                first_page = docs[0].page_content[:300]
                metadata['preview'] = first_page.replace('\n', ' ').strip()
            
            return metadata
        except Exception as e:
            return {'error': f"Failed to extract metadata: {str(e)}"}
    
    def process_pdf(self, pdf_path: str) -> List[Document]:
        """Process PDF with chunking."""
        try:
            loader = PyMuPDFLoader(pdf_path)
            raw_docs = loader.load()
            
            processed_docs = self.text_splitter.split_documents(raw_docs)
            
            for i, doc in enumerate(processed_docs):
                doc.metadata.update({
                    'source_file': pdf_path,
                    'chunk_index': i,
                    'total_chunks': len(processed_docs)
                })
            
            return processed_docs
            
        except Exception as e:
            print(f"[ERROR] PDF processing failed: {str(e)}")
            return []
    
    def load_content(self, pdf_path: Optional[str] = None) -> List[str]:
        """Load and process a PDF document into text chunks."""
        try:
            if not pdf_path:
                found_path = self.auto_find_pdf()
                if not found_path:
                    available_pdfs = self.find_pdf_files()
                    if available_pdfs:
                        return [f"No PDF specified. Available PDFs: {', '.join(os.path.basename(p) for p in available_pdfs[:5])}{'...' if len(available_pdfs) > 5 else ''}"]
                    else:
                        return ["Error: No PDF files found in models directory"]
                pdf_path = found_path
            else:
                pdf_path = self.normalize_pdf_path(pdf_path)
                
                if not os.path.exists(pdf_path):
                    found_path = self.auto_find_pdf(os.path.basename(pdf_path))
                    if found_path:
                        pdf_path = found_path
                    else:
                        available_pdfs = self.find_pdf_files()
                        if available_pdfs:
                            return [f"Error: PDF file not found at {pdf_path}. Available PDFs: {', '.join(os.path.basename(p) for p in available_pdfs[:3])}"]
                        else:
                            return [f"Error: PDF file not found at {pdf_path} and no PDFs available"]
            
            documents = self.process_pdf(pdf_path)
            
            if not documents:
                return ["Error: Processing failed"]
            
            chunks = [doc.page_content for doc in documents]
            if chunks:
                chunks.insert(0, f"Source: {pdf_path}")
            
            return chunks
            
        except Exception as e:
            return [f"Error loading PDF: {str(e)}"]
    
    def analyze_content(self, pdf_path: Optional[str] = None, query: str = "") -> Dict[str, Any]:
        """Analyze PDF content with categorized information extraction."""
        try:
            if not pdf_path:
                found_path = self.auto_find_pdf()
                if not found_path:
                    return {"error": "No PDF file found"}
                pdf_path = found_path
            else:
                pdf_path = self.normalize_pdf_path(pdf_path)
                if not os.path.exists(pdf_path):
                    found_path = self.auto_find_pdf(os.path.basename(pdf_path))
                    if found_path:
                        pdf_path = found_path
                    else:
                        return {"error": f"PDF file not found at {pdf_path}"}
            
            # Extract metadata
            metadata = self.extract_metadata(pdf_path)
            
            # Process PDF
            documents = self.process_pdf(pdf_path)
            
            if not documents:
                return {"error": "Processing failed"}
            
            # Create analysis result
            analysis_result = {
                "source_file": pdf_path,
                "metadata": metadata,
                "total_chunks": len(documents),
                "content_summary": {},
                "extracted_sections": [],
                "analysis_status": "completed"
            }
            
            # Content categorization
            categories = {
                "architecture": ["architecture", "model", "framework", "structure", "design", "network", "layer"],
                "methodology": ["method", "approach", "algorithm", "technique", "procedure", "pipeline"],
                "preprocessing": ["preprocessing", "preprocess", "data preparation", "cleaning", "normalization", "feature"],
                "hyperparameters": ["hyperparameter", "parameter", "learning rate", "batch size", "epoch", "optimizer"],
                "dependencies": ["import", "library", "package", "requirement", "dependency", "framework"],
                "implementation": ["code", "implementation", "function", "class", "module", "script"],
                "evaluation": ["evaluation", "metrics", "performance", "accuracy", "validation", "testing"],
                "results": ["results", "findings", "conclusion", "outcome", "performance", "benchmark"]
            }
            
            # Analyze content
            content_text = " ".join([doc.page_content for doc in documents]).lower()
            
            for category, keywords in categories.items():
                matches = []
                relevance_score = 0
                
                for keyword in keywords:
                    count = content_text.count(keyword)
                    if count > 0:
                        matches.append({"keyword": keyword, "count": count})
                        relevance_score += count
                
                analysis_result["content_summary"][category] = {
                    "relevance_score": relevance_score,
                    "keyword_matches": matches,
                    "confidence": min(relevance_score / 10.0, 1.0)
                }
            
            # Extract key sections
            for i, doc in enumerate(documents[:10]):
                if len(doc.page_content) > 200:
                    section_info = {
                        "chunk_index": i,
                        "page": doc.metadata.get('page', 'unknown'),
                        "preview": doc.page_content[:200] + "...",
                        "length": len(doc.page_content)
                    }
                    analysis_result["extracted_sections"].append(section_info)
            
            # Query-specific analysis if provided
            if query:
                analysis_result["query_analysis"] = {
                    "query": query,
                    "relevant_chunks": []
                }
                
                query_lower = query.lower()
                for i, doc in enumerate(documents):
                    if query_lower in doc.page_content.lower():
                        analysis_result["query_analysis"]["relevant_chunks"].append({
                            "chunk_index": i,
                            "relevance_snippet": doc.page_content[:300] + "..."
                        })
            
            return analysis_result
            
        except Exception as e:
            return {"error": f"Analysis failed: {str(e)}"}
    
    def create_retriever(self, pdf_path: Optional[str] = None, collection_name: str = "paper_analysis"):
        """Create RAG retriever from PDF document."""
        try:
            if not pdf_path:
                found_path = self.auto_find_pdf()
                if not found_path:
                    return "Error: No PDF file found"
                pdf_path = found_path
            else:
                pdf_path = self.normalize_pdf_path(pdf_path)
                if not os.path.exists(pdf_path):
                    found_path = self.auto_find_pdf(os.path.basename(pdf_path))
                    if found_path:
                        pdf_path = found_path
                    else:
                        return f"Error: PDF file not found at {pdf_path}"
            
            documents = self.process_pdf(pdf_path)
            if not documents:
                return "Error: No documents processed"
            
            vectorstore = Chroma(
                collection_name=collection_name, 
                embedding_function=self.embeddings
            )
            
            vectorstore.add_documents(documents)
            return vectorstore.as_retriever(search_kwargs={'k': 8})
            
        except Exception as e:
            return f"Error creating RAG retriever: {str(e)}"


# Global PDF analyzer instance
_pdf_analyzer = None

def get_pdf_analyzer() -> PDFAnalyzer:
    """Get singleton PDF analyzer instance."""
    global _pdf_analyzer
    if _pdf_analyzer is None:
        _pdf_analyzer = PDFAnalyzer()
    return _pdf_analyzer