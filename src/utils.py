import os
import glob
import hashlib
import threading
from typing import List, Dict, Any, Optional
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from langchain_core.tools import tool
from datetime import datetime


class GlobalStateManager:
    """Simplified thread-safe state manager for AutoDRP agents."""
    
    _lock = threading.Lock()
    _state = None
    
    @classmethod
    def initialize(cls):
        """Initialize the global state with an empty dict."""
        with cls._lock:
            if cls._state is None:
                cls._state = {
                    'pdf_analysis': None,
                    'preprocessing_progress': {},
                    'current_agent_tasks': {},
                    'agent_results': {},
                    'handoff_context': {}
                }
                print("[GlobalStateManager] State initialized")
    
    @classmethod
    def get_state(cls):
        """Get the current global state as a dict."""
        with cls._lock:
            if cls._state is None:
                cls.initialize()
            return cls._state.copy()
    
    @classmethod
    def update_state(cls, new_state, operation="UPDATE", agent="unknown"):
        """Update the global state."""
        with cls._lock:
            if cls._state is None:
                cls.initialize()
            
            # Simple dict-based update
            if isinstance(new_state, dict):
                cls._state.update(new_state)
                print(f"✅ State updated by {agent}")
                return cls._state.copy()
            else:
                print(f"❌ Expected dict, got {type(new_state)}")
                return cls._state.copy()
    
    @classmethod
    def get_summary(cls) -> str:
        """Get a summary of the current state."""
        state = cls.get_state()
        info = []
        info.append(f"📊 Global State Summary:")
        info.append(f"PDF Analysis: {'Available' if state.get('pdf_analysis') else 'None'}")
        info.append(f"Preprocessing Steps: {len(state.get('preprocessing_progress', {}))}")
        info.append(f"Current Tasks: {len(state.get('current_agent_tasks', {}))}")
        info.append(f"Agent Results: {len(state.get('agent_results', {}))}")
        
        current_tasks = state.get('current_agent_tasks', {})
        if current_tasks:
            info.append("\n🔄 Active Tasks:")
            for agent, task in current_tasks.items():
                info.append(f"  - {agent}: {task}")
        
        return "\n".join(info)


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
        # Caching for analysis results
        self._analysis_cache: Dict[str, Dict[str, Any]] = {}
        self._documents_cache: Dict[str, List[Document]] = {}
    
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
    
    def _resolve_pdf_path(self, pdf_path: Optional[str] = None) -> Optional[str]:
        """Resolve PDF path with fallback logic and validation."""
        if not pdf_path:
            return self.auto_find_pdf()
        
        # Normalize path
        if not os.path.isabs(pdf_path):
            if not (pdf_path.startswith('./models/') or pdf_path.startswith('models/')):
                pdf_path = os.path.join(self.base_dir, pdf_path)
        
        # Check if exists, if not try to find it
        if os.path.exists(pdf_path):
            return pdf_path
        
        return self.auto_find_pdf(os.path.basename(pdf_path))
    
    def _get_file_cache_key(self, pdf_path: str) -> str:
        """Generate cache key based on file path and modification time."""
        try:
            mtime = os.path.getmtime(pdf_path)
            # Use file path and modification time for cache key
            return hashlib.md5(f"{pdf_path}_{mtime}".encode()).hexdigest()
        except OSError:
            # If file doesn't exist, return path-only hash
            return hashlib.md5(pdf_path.encode()).hexdigest()
    
    def _is_cache_valid(self, pdf_path: str, cache_key: str) -> bool:
        """Check if cached result is still valid."""
        current_key = self._get_file_cache_key(pdf_path)
        return cache_key == current_key
    
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
        """Process PDF with chunking and caching."""
        try:
            # Check cache first
            cache_key = self._get_file_cache_key(pdf_path)
            
            if cache_key in self._documents_cache:
                if self._is_cache_valid(pdf_path, cache_key):
                    return self._documents_cache[cache_key]
                else:
                    # Remove invalid cache entry
                    del self._documents_cache[cache_key]
            
            # Process PDF if not cached
            loader = PyMuPDFLoader(pdf_path)
            raw_docs = loader.load()
            
            processed_docs = self.text_splitter.split_documents(raw_docs)
            
            for i, doc in enumerate(processed_docs):
                doc.metadata.update({
                    'source_file': pdf_path,
                    'chunk_index': i,
                    'total_chunks': len(processed_docs)
                })
            
            # Cache the results
            self._documents_cache[cache_key] = processed_docs
            
            return processed_docs
            
        except Exception as e:
            print(f"[ERROR] PDF processing failed: {str(e)}")
            return []
    
    def load_content(self, pdf_path: Optional[str] = None) -> List[str]:
        """Load and process a PDF document into text chunks."""
        try:
            resolved_path = self._resolve_pdf_path(pdf_path)
            if not resolved_path:
                available_pdfs = self.find_pdf_files()
                if available_pdfs:
                    return [f"No PDF found. Available: {', '.join(os.path.basename(p) for p in available_pdfs[:3])}"]
                return ["Error: No PDF files found in models directory"]
            
            documents = self.process_pdf(resolved_path)
            if not documents:
                return ["Error: Processing failed"]
            
            chunks = [doc.page_content for doc in documents]
            chunks.insert(0, f"Source: {resolved_path}")
            return chunks
            
        except Exception as e:
            return [f"Error loading PDF: {str(e)}"]
    
    def analyze_content(self, pdf_path: Optional[str] = None, query: str = "") -> Dict[str, Any]:
        """Analyze PDF content with categorized information extraction and caching."""
        try:
            resolved_path = self._resolve_pdf_path(pdf_path)
            if not resolved_path:
                return {"error": "No PDF file found"}
            
            # Check cache first
            cache_key = self._get_file_cache_key(resolved_path)
            query_cache_key = f"{cache_key}_{hashlib.md5(query.encode()).hexdigest()}"
            
            if query_cache_key in self._analysis_cache:
                if self._is_cache_valid(resolved_path, cache_key):
                    return self._analysis_cache[query_cache_key]
                else:
                    # Remove invalid cache entries
                    keys_to_remove = [k for k in self._analysis_cache.keys() if k.startswith(cache_key)]
                    for k in keys_to_remove:
                        del self._analysis_cache[k]
            
            # Extract metadata and process PDF (cached in process_pdf)
            metadata = self.extract_metadata(resolved_path)
            documents = self.process_pdf(resolved_path)
            
            if not documents:
                return {"error": "Processing failed"}
            
            # Create analysis result
            analysis_result = {
                "source_file": resolved_path,
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
            
            # Cache the analysis result
            self._analysis_cache[query_cache_key] = analysis_result
            
            return analysis_result
            
        except Exception as e:
            return {"error": f"Analysis failed: {str(e)}"}
    
    
    def create_retriever(self, pdf_path: Optional[str] = None, collection_name: str = "paper_analysis"):
        """Create RAG retriever from PDF document."""
        try:
            resolved_path = self._resolve_pdf_path(pdf_path)
            if not resolved_path:
                return "Error: No PDF file found"
            
            documents = self.process_pdf(resolved_path)
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
    """Get singleton PDF analyzer instance with cross-session caching support."""
    global _pdf_analyzer
    if _pdf_analyzer is None:
        _pdf_analyzer = PDFAnalyzer()
    return _pdf_analyzer

def clear_pdf_cache():
    """Clear all PDF analysis caches (useful for testing or memory management)."""
    global _pdf_analyzer
    if _pdf_analyzer is not None:
        _pdf_analyzer._analysis_cache.clear()
        _pdf_analyzer._documents_cache.clear()

def get_cache_stats() -> Dict[str, int]:
    """Get current cache statistics for monitoring."""
    global _pdf_analyzer
    if _pdf_analyzer is None:
        return {"analysis_cache": 0, "documents_cache": 0}
    
    return {
        "analysis_cache": len(_pdf_analyzer._analysis_cache),
        "documents_cache": len(_pdf_analyzer._documents_cache)
    }


def get_pdf_tools():
    """Get PDF-related LangChain tools for agent use."""
    pdf_analyzer = get_pdf_analyzer()
    
    def _handle_pdf_error(error_msg: str = "No PDF files found in models directory") -> str:
        """Common error handling for PDF operations."""
        return error_msg
    
    def _update_state_with_pdf_analysis(pdf_path: str, analysis_data: Dict[str, Any]):
        """Update state with PDF analysis results."""
        try:
            current_state = GlobalStateManager.get_state()
            from .state import StateManager
            updated_state = StateManager.update_pdf_analysis(current_state, pdf_path, analysis_data)
            GlobalStateManager.update_state(updated_state, "PDF_ANALYSIS", "analyzing_agent")
            print(f"✅ PDF analysis saved to state: {os.path.basename(pdf_path)}")
            return True
        except Exception as e:
            print(f"❌ Failed to update state with PDF analysis: {e}")
        return False
    
    @tool
    def analyze_pdfs(query: str = "") -> str:
        """Analyze PDF documents in models directory with optional query focus and caching."""
        try:
            pdf_files = pdf_analyzer.find_pdf_files()
            if not pdf_files:
                return _handle_pdf_error()
            
            results = []
            cache_hits = 0
            state_updates = 0
            
            for pdf_path in pdf_files[:3]:  # Limit to 3 PDFs for better performance
                pdf_name = os.path.basename(pdf_path)
                
                # Check if result is cached (quick check)
                cache_key = pdf_analyzer._get_file_cache_key(pdf_path)
                query_cache_key = f"{cache_key}_{hashlib.md5(query.encode()).hexdigest()}"
                
                if query_cache_key in pdf_analyzer._analysis_cache:
                    cache_hits += 1
                
                analysis = pdf_analyzer.analyze_content(pdf_path, query)
                
                if "error" not in analysis:
                    total_chunks = analysis.get('total_chunks', 0)
                    arch_score = analysis.get('content_summary', {}).get('architecture', {}).get('relevance_score', 0)
                    method_score = analysis.get('content_summary', {}).get('methodology', {}).get('relevance_score', 0)
                    cache_indicator = "🔄" if query_cache_key in pdf_analyzer._analysis_cache else "🆕"
                    
                    # Update state with analysis results
                    if _update_state_with_pdf_analysis(pdf_path, analysis):
                        state_updates += 1
                        cache_indicator += "💾"
                    
                    results.append(f"{cache_indicator} {pdf_name}: {total_chunks} chunks, Architecture: {arch_score}, Methodology: {method_score}")
                else:
                    results.append(f"❌ {pdf_name}: {analysis['error']}")
            
            summary = f"Analyzed {len(pdf_files[:3])} PDFs ({cache_hits} cached, {state_updates} saved to state)\n" + "\n".join(results)
            return summary
        except Exception as e:
            return f"Error analyzing PDFs: {str(e)}"
    
    @tool
    def find_pdf_files() -> str:
        """Find all available PDF files in the models directory."""
        try:
            pdf_files = pdf_analyzer.find_pdf_files()
            if not pdf_files:
                return _handle_pdf_error()
            
            file_list = [f"📄 {os.path.basename(p)} ({os.path.getsize(p) // 1024}KB)" for p in pdf_files]
            return f"Found {len(pdf_files)} PDF files:\n" + "\n".join(file_list)
        except Exception as e:
            return f"Error finding PDFs: {str(e)}"
    
    @tool
    def get_pdf_summary(pdf_name: str = "") -> str:
        """Get detailed summary of a specific PDF file."""
        try:
            if not pdf_name:
                return "Please specify a PDF filename"
            
            analysis = pdf_analyzer.analyze_content(pdf_name)
            if "error" in analysis:
                return f"Error: {analysis['error']}"
            
            summary = [
                f"📄 File: {os.path.basename(analysis['source_file'])}",
                f"📊 Total chunks: {analysis.get('total_chunks', 0)}"
            ]
            
            # Add category scores
            content_summary = analysis.get('content_summary', {})
            for category, data in content_summary.items():
                score = data.get('relevance_score', 0)
                if score > 0:
                    summary.append(f"🔍 {category.title()}: {score} matches")
            
            # Add sections info
            sections = analysis.get('extracted_sections', [])
            if sections:
                summary.append(f"📋 Key sections: {len(sections)} found")
            
            # Update state with analysis results
            pdf_path = analysis['source_file']
            if _update_state_with_pdf_analysis(pdf_path, analysis):
                summary.append("💾 Analysis saved to state")
            
            return "\n".join(summary)
        except Exception as e:
            return f"Error getting PDF summary: {str(e)}"
    
    return [analyze_pdfs, find_pdf_files, get_pdf_summary]


def get_state_tools():
    """Get simplified state management tools for agent use."""
    from .state import StateManager
    
    @tool
    def save_agent_result(agent_name: str, result_data: str) -> str:
        """Save agent result data to global state."""
        try:
            current_state = GlobalStateManager.get_state()
            
            # Parse result_data as JSON if possible, otherwise store as string
            import json
            try:
                parsed_data = json.loads(result_data)
            except:
                parsed_data = {"result": result_data}
            
            updated_state = StateManager.update_agent_result(current_state, agent_name, parsed_data)
            GlobalStateManager.update_state(updated_state, "SAVE_RESULT", agent_name)
            
            return f"✅ Agent result saved: {agent_name}"
            
        except Exception as e:
            return f"❌ Error saving result: {str(e)}"
    
    @tool
    def get_agent_result(agent_name: str) -> str:
        """Get agent result data from global state."""
        try:
            current_state = GlobalStateManager.get_state()
            agent_results = current_state.get('agent_results', {})
            
            if agent_name in agent_results:
                import json
                return json.dumps(agent_results[agent_name], indent=2)
            else:
                return f"No results found for agent: {agent_name}"
                
        except Exception as e:
            return f"❌ Error getting result: {str(e)}"
    
    @tool
    def set_handoff_info(from_agent: str, to_agent: str, context: str) -> str:
        """Set handoff information for agent transition."""
        try:
            current_state = GlobalStateManager.get_state()
            
            # Parse context as JSON if possible
            import json
            try:
                context_data = json.loads(context)
            except:
                context_data = {"message": context}
            
            updated_state = StateManager.update_handoff_context(current_state, from_agent, to_agent, context_data)
            GlobalStateManager.update_state(updated_state, "HANDOFF", from_agent)
            
            return f"✅ Handoff info set: {from_agent} → {to_agent}"
            
        except Exception as e:
            return f"❌ Error setting handoff: {str(e)}"
    
    @tool
    def get_handoff_info() -> str:
        """Get current handoff information."""
        try:
            current_state = GlobalStateManager.get_state()
            handoff_context = current_state.get('handoff_context', {})
            
            if handoff_context:
                import json
                return json.dumps(handoff_context, indent=2)
            else:
                return "No handoff information available"
                
        except Exception as e:
            return f"❌ Error getting handoff info: {str(e)}"
    
    @tool
    def view_current_state() -> str:
        """View current global state information."""
        try:
            return GlobalStateManager.get_summary()
        except Exception as e:
            return f"❌ Error viewing state: {str(e)}"
    
    return [save_agent_result, get_agent_result, set_handoff_info, get_handoff_info, view_current_state]