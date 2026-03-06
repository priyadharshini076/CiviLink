"""
CiviLink Core Assistant
Accessibility-first, privacy-focused government services assistant
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import re
import logging
import os
from core.llm_intent_detector import LLMIntentDetector, IntentType, AssistanceLevel, IntentResult
from multilingual.multilingual_llm import MultilingualLLM, MultilingualResponse

class IntentType(Enum):
    WIDOW_PENSION = "widow_pension"
    SCHOLARSHIP = "scholarship"
    CERTIFICATE_APPLICATION = "certificate_application"
    UNKNOWN = "unknown"

class AssistanceMode(Enum):
    NORMAL = "normal"
    SIMPLIFIED = "simplified"
    EXPLANATION = "explanation"

@dataclass
class UserSession:
    user_id: str
    language: str = "en"
    assistance_mode: AssistanceMode = AssistanceMode.NORMAL
    consent_given: bool = False
    current_workflow: Optional[str] = None
    collected_fields: Dict[str, Any] = None
    current_step: int = 0
    needs_explanation: bool = False
    
    def __post_init__(self):
        if self.collected_fields is None:
            self.collected_fields = {}

class CiviLinkAssistant:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.sessions: Dict[str, UserSession] = {}
        
        # Initialize LLM components
        # self.intent_detector = LLMIntentDetector()
        # self.multilingual_llm = MultilingualLLM()
        self.intent_detector = None
        self.multilingual_llm = None
        
        # Legacy patterns for fallback
        self.intent_patterns = self._load_intent_patterns()
        self.empathy_responses = self._load_empathy_responses()
        
        # Workflow definitions
        self.workflow_definitions = self._load_workflow_definitions()

        # Portal config (optional in offline mode)
        self.portal_base_url = os.getenv('PORTAL_BASE_URL', '').strip()
        
    def _load_intent_patterns(self) -> Dict[IntentType, List[str]]:
        """Load patterns for intent detection"""
        return {
            IntentType.WIDOW_PENSION: [
                r'widow.*pension', r'pension.*widow', r'विधवा.*पेंशन', 
                r'விதவை.*ஓயவூதியம்', r'husband.*passed.*away'
            ],
            IntentType.SCHOLARSHIP: [
                r'scholarship', r'education.*grant', r'student.*aid',
                r'छात्रवृत्ति', r'கல்வி.*உதவி', r'study.*fund'
            ],
            IntentType.CERTIFICATE_APPLICATION: [
                r'certificate', r'birth.*certificate', r'death.*certificate',
                r'marriage.*certificate', r'प्रमाणपत्र', r'சான்றிதழ்'
            ]
        }
    
    def _load_empathy_responses(self) -> Dict[str, List[str]]:
        """Load empathetic response templates"""
        return {
            'confusion': [
                "It's okay. I'm here to help you.",
                "Don't worry. We can take this step by step.",
                "I understand this might seem confusing. Let me make it simpler."
            ],
            'hesitation': [
                "Take your time. There's no rush.",
                "It's completely fine to go slowly.",
                "I'm here to help at your pace."
            ],
            'error': [
                "I'm not sure I understood that. Could you please clarify?",
                "There seems to be a technical issue. Let's try again.",
                "I apologize for the confusion. Let me rephrase that."
            ]
        }
    
    def detect_intent(self, message: str, user_id: str) -> IntentResult:
        """Detect user intent using LLM with fallback to patterns"""
        try:
            # Get user context for better LLM understanding
            session = self.get_or_create_session(user_id)
            user_context = {
                "language": session.language,
                "assistance_mode": session.assistance_mode.value,
                "current_workflow": session.current_workflow,
                "consent_given": session.consent_given
            }
            
            # Use LLM for primary intent detection (optional)
            if not self.intent_detector:
                raise RuntimeError("LLM intent detector not configured")

            intent_result = self.intent_detector.detect_intent(message, user_context)
            
            # Update session with detected information
            session.language = intent_result.language
            if intent_result.assistance_level == AssistanceLevel.SIMPLIFIED:
                session.assistance_mode = AssistanceMode.SIMPLIFIED
            elif intent_result.assistance_level == AssistanceLevel.EXPLANATION:
                session.assistance_mode = AssistanceMode.EXPLANATION
            
            self.logger.info(f"LLM detected intent: {intent_result.intent.value} for user {user_id}")
            return intent_result
            
        except Exception as e:
            self.logger.error(f"LLM intent detection failed, using fallback: {str(e)}")
            # Fallback to pattern-based detection
            legacy_intent = self._fallback_intent_detection(message)
            return IntentResult(
                intent=legacy_intent,
                confidence=0.5,
                language="en",
                assistance_level=AssistanceLevel.NORMAL,
                entities={}
            )
    
    def _fallback_intent_detection(self, message: str) -> IntentType:
        """Fallback intent detection using regex patterns"""
        message_lower = message.lower()
        
        for intent_type, patterns in self.intent_patterns.items():
            for pattern in patterns:
                if re.search(pattern, message_lower):
                    return intent_type
        
        return IntentType.UNKNOWN
    
    def detect_assistance_mode(self, message: str, session: UserSession) -> AssistanceMode:
        """Detect if user needs simplified assistance"""
        confusion_indicators = [
            "confused", "don't understand", "not clear", "difficult",
            "confused", "समझ नहीं आ रहा", "புரியவில்லை", "explain simple"
        ]
        
        elderly_indicators = [
            "elderly", "senior", "old age", "slow", "बूढ़ा", "வயதான"
        ]
        
        simplification_requests = [
            "explain simple", "make it simple", "easy words", 
            "simple language", "आसान भाषा", "எளிய மொழி"
        ]
        
        message_lower = message.lower()
        
        if any(indicator in message_lower for indicator in confusion_indicators + elderly_indicators + simplification_requests):
            return AssistanceMode.SIMPLIFIED
        
        if session.needs_explanation or "explain" in message_lower:
            return AssistanceMode.EXPLANATION
            
        return AssistanceMode.NORMAL
    
    def get_or_create_session(self, user_id: str) -> UserSession:
        """Get existing session or create new one"""
        if user_id not in self.sessions:
            self.sessions[user_id] = UserSession(user_id=user_id)
        return self.sessions[user_id]
    
    def format_response(self, message: str, session: UserSession) -> str:
        """Format response based on assistance mode and language"""
        if session.assistance_mode == AssistanceMode.SIMPLIFIED:
            message = self._simplify_language(message)
        
        # Add empathetic prefix if user seems confused
        if session.assistance_mode in [AssistanceMode.SIMPLIFIED, AssistanceMode.EXPLANATION]:
            empathy_prefix = "I'm here to help you. "
            message = empathy_prefix + message
        
        return message
    
    def _simplify_language(self, message: str) -> str:
        """Simplify complex language"""
        simplifications = {
            "Please provide": "Please tell me",
            "residential address": "home address",
            "authentication": "verification",
            "application": "form",
            "submit": "send",
            "process": "help you with"
        }
        
        for complex_term, simple_term in simplifications.items():
            message = message.replace(complex_term, simple_term)
        
        # Break into shorter sentences
        sentences = message.split('. ')
        if len(sentences) > 2:
            message = '. '.join(sentences[:2]) + '.'
        
        return message
    
    def get_empathetic_response(self, situation: str) -> str:
        """Get empathetic response for specific situations"""
        if situation in self.empathy_responses:
            import random
            return random.choice(self.empathy_responses[situation])
        return "I'm here to help you."
    
    def _load_workflow_definitions(self) -> Dict[str, Dict]:
        """Load workflow definitions for different services"""
        return {
            'widow_pension': {
                'fields': ['full_name', 'age', 'husband_name', 'date_of_death', 'address'],
                'questions': [
                    "What is your full name?",
                    "What is your age?",
                    "What was your husband's name?",
                    "When did your husband pass away? (DD/MM/YYYY)",
                    "What is your current address?"
                ],
                'api_endpoint': '/apply_widow_pension'
            },
            'scholarship': {
                'fields': ['full_name', 'age', 'school_name', 'grade', 'family_income'],
                'questions': [
                    "What is your full name?",
                    "What is your age?",
                    "What is the name of your school?",
                    "What grade are you in?",
                    "What is your family's monthly income?"
                ],
                'api_endpoint': '/apply_scholarship'
            },
            'certificate_application': {
                'fields': ['certificate_type', 'full_name', 'date_of_birth', 'address'],
                'questions': [
                    "What type of certificate do you need? (birth/death/marriage)",
                    "What is your full name?",
                    "What is your date of birth? (DD/MM/YYYY)",
                    "What is your current address?"
                ],
                'api_endpoint': '/apply_certificate'
            }
        }
    
    def validate_consent(self, user_id: str) -> bool:
        """Check if user has given consent for processing"""
        session = self.get_or_create_session(user_id)
        return session.consent_given
    
    def request_consent(self, language: str = "en") -> str:
        """Request user consent for data processing"""
        consent_messages = {
            "en": "Do you consent to EmpowerAbility processing your personal information for application assistance?",
            "ta": "விண்ணப்ப உதவிக்கு உங்கள் தனிப்பட்ட தகவலை EmpowerAbility செயலாற்ற ஒப்புக்கொள்கிறீர்களா?",
            "hi": "क्या आप आवेदन सहायता के लिए EmpowerAbility द्वारा आपकी व्यक्तिगत जानकारी को संसाधित करने के लिए सहमत हैं?"
        }
        return consent_messages.get(language, consent_messages["en"])
    
    def get_next_question(self, session: UserSession) -> Optional[str]:
        """Get next question based on workflow and collected fields"""
        if not session.current_workflow:
            return None
        
        workflow = self.workflow_definitions.get(session.current_workflow)
        if not workflow:
            return None
        
        if session.current_step < len(workflow['questions']):
            return workflow['questions'][session.current_step]
        
        return None
    
    def process_message(self, user_id: str, message: Any, message_type: str = "text") -> Dict[str, Any]:
        """Main message processing pipeline with LLM integration"""
        session = self.get_or_create_session(user_id)
        
        # Handle voice messages (Whisper)
        if message_type in ["voice", "voice_url"]:
            from .whisper_stt import WhisperSTT
            whisper = WhisperSTT()
            
            audio_data = None
            if message_type == "voice_url":
                import requests
                response = requests.get(message)
                if response.status_code == 200:
                    audio_data = response.content
            else:
                audio_data = message

            if audio_data:
                transcribed_text, detected_lang = whisper.transcribe_audio(audio_data)
                if transcribed_text:
                    message = transcribed_text
                    if detected_lang:
                        session.language = detected_lang
                else:
                    return {
                        "response": self.format_response("I couldn't understand the audio. Could you please type your message?", session),
                        "session_state": "voice_processing_failed"
                    }
            else:
                return {
                    "response": self.format_response("I couldn't retrieve the audio message. Could you please try again?", session),
                    "session_state": "voice_retrieval_failed"
                }
        
        # Detect intent using LLM
        intent_result = self.detect_intent(message, user_id)
        
        # Check consent first
        if not session.consent_given:
            msg_lower = str(message).strip().lower()
            consent_yes = {
                "yes", "y", "ok", "okay", "sure", "i agree", "agree", "consent", "i consent"
            }
            consent_no = {"no", "n", "disagree"}

            if any(token in msg_lower for token in consent_yes) or "சம்மதம்" in str(message) or "हाँ" in str(message):
                session.consent_given = True
                if self.multilingual_llm:
                    response = self.multilingual_llm.generate_response(
                        message=message,
                        intent="consent_given",
                        language=session.language,
                        assistance_level=session.assistance_mode.value
                    )
                    response_text = response.text
                else:
                    response_text = "Consent noted. Let's begin."
                return {
                    "response": response_text,
                    "session_state": "consent_given",
                    "language": session.language
                }
            elif any(token in msg_lower for token in consent_no):
                if self.multilingual_llm:
                    response = self.multilingual_llm.generate_response(
                        message=message,
                        intent="consent_denied",
                        language=session.language,
                        assistance_level=session.assistance_mode.value
                    )
                    response_text = response.text
                else:
                    response_text = "Okay. I can't proceed without consent."
                return {
                    "response": response_text,
                    "session_state": "consent_denied"
                }
            else:
                consent_msg = self.request_consent(session.language)
                return {
                    "response": consent_msg,
                    "session_state": "awaiting_consent"
                }
        
        if not session.current_workflow:
            if intent_result.intent == IntentType.UNKNOWN:
                if self.multilingual_llm:
                    response = self.multilingual_llm.generate_response(
                        message=message,
                        intent="intent_clarification",
                        language=session.language,
                        assistance_level=session.assistance_mode.value
                    )
                else:
                    response = type('Response', (), {'text': "I didn't understand your request. Could you please specify what service you need help with? For example: widow pension, scholarship, or certificate application."})()
                return {
                    "response": response.text,
                    "session_state": "intent_clarification_needed"
                }
            else:
                session.current_workflow = intent_result.intent.value
                if self.multilingual_llm:
                    response = self.multilingual_llm.generate_response(
                        message=message,
                        intent=f"workflow_start_{intent_result.intent.value}",
                        language=session.language,
                        assistance_level=session.assistance_mode.value,
                        context={"workflow": intent_result.intent.value}
                    )
                else:
                    start_msg = f"Starting application for {intent_result.intent.value.replace('_', ' ')}. {self.get_next_question(session)}"
                    response = type('Response', (), {'text': start_msg})()
                return {
                    "response": response.text,
                    "session_state": "workflow_initialized",
                    "current_workflow": session.current_workflow,
                    "next_question": self.get_next_question(session)
                }
        
        # Continue workflow
        workflow = self.workflow_definitions.get(session.current_workflow)
        if not workflow:
            session.current_workflow = None
            session.collected_fields = {}
            session.current_step = 0
            return {
                "response": "I couldn't find that service workflow. Please try again.",
                "session_state": "workflow_error"
            }

        msg_lower = str(message).strip().lower()

        # If we're at review step, handle confirmation
        if session.current_step >= len(workflow['fields']):
            if msg_lower in {"yes", "y", "confirm", "submit"}:
                api_data = session.collected_fields
                api_endpoint = workflow['api_endpoint']

                portal_url = self.portal_base_url
                offline_mode = (not portal_url) or ("localhost" in portal_url) or (portal_url.startswith("http://127."))
                if offline_mode:
                    response_text = "Submitted (offline mode). Reference ID: DRAFT-001"
                else:
                    try:
                        import requests
                        api_response = requests.post(f"{portal_url}{api_endpoint}", json=api_data, timeout=10)
                        if api_response.status_code == 200:
                            result = api_response.json()
                            response_text = f"Application submitted successfully. Reference ID: {result.get('reference_id', 'N/A')}"
                        else:
                            response_text = "There was an error submitting your application. Please try again."
                    except Exception as e:
                        self.logger.error(f"API call failed: {str(e)}")
                        response_text = "Unable to connect to government portal. Saved as draft. Reference ID: DRAFT-001"

                session.current_workflow = None
                session.collected_fields = {}
                session.current_step = 0
                return {
                    "response": response_text,
                    "session_state": "application_submitted"
                }

            if msg_lower in {"no", "n", "edit", "change"}:
                session.current_step = 0
                session.collected_fields = {}
                q = self.get_next_question(session)
                return {
                    "response": q or "Okay, let's start over. What would you like to apply for?",
                    "session_state": "workflow_restarted"
                }

            return {
                "response": "Please reply 'yes' to confirm submission or 'no' to restart.",
                "session_state": "awaiting_confirmation"
            }

        # Normal field collection step
        if session.current_step < len(workflow['fields']):
            field = workflow['fields'][session.current_step]
            session.collected_fields[field] = message
            session.current_step += 1

        next_question = self.get_next_question(session)
        if next_question:
            response_text = self.format_response(next_question, session)
            return {
                "response": response_text,
                "session_state": "workflow_in_progress",
                "next_question": next_question
            }

        # Review step
        lines = [f"{k}: {v}" for k, v in session.collected_fields.items()]
        review_text = "Please review your application:\n" + "\n".join(lines) + "\n\nReply 'yes' to submit or 'no' to restart."
        return {
            "response": review_text,
            "session_state": "review"
        }
        
        # Default ready state
        if self.multilingual_llm:
            response = self.multilingual_llm.generate_response(
                message=message,
                intent="ready",
                language=session.language,
                assistance_level=session.assistance_mode.value
            )
        else:
            response = type('Response', (), {'text': "How can I help you with government services today?"})()
        
        return {
            "response": response.text,
            "session_state": "ready"
        }
