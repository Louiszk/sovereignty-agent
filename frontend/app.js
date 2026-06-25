document.addEventListener('DOMContentLoaded', () => {
    const sessionId = Date.now().toString() + Math.random().toString(36).substring(7);
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const chatContainer = document.getElementById('chat-container');

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const message = userInput.value.trim();
        if (!message) return;

        // Add user message
        appendMessage('user', message);
        userInput.value = '';

        // Add loading indicator
        const loadingId = appendLoading();

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message, session_id: sessionId })
            });

            const data = await response.json();
            
            // Remove loading
            document.getElementById(loadingId).remove();
            
            // Add AI response
            appendMessage('assistant', data.reply);
        } catch (error) {
            document.getElementById(loadingId).remove();
            appendMessage('assistant', 'Sorry, es gab einen Fehler bei der Verbindung zum Server.');
            console.error('Error:', error);
        }
    });

    function appendMessage(role, content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        
        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'avatar';
        avatarDiv.textContent = role === 'user' ? 'USER' : 'AI';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'content';
        
        // Parse markdown for AI responses
        if (role === 'assistant') {
            const processedContent = content.replace(/\[\[(CHK-[^\]]+)\]\]/g, '<span class="citation-badge" data-chunk="$1">📄 $1</span>');
            const rawHtml = marked.parse(processedContent);
            contentDiv.innerHTML = DOMPurify.sanitize(rawHtml);
            
            // Add event listeners to citations
            const badges = contentDiv.querySelectorAll('.citation-badge');
            badges.forEach(badge => {
                badge.addEventListener('click', () => openModal(badge.getAttribute('data-chunk')));
            });
        } else {
            contentDiv.textContent = content;
        }

        messageDiv.appendChild(avatarDiv);
        messageDiv.appendChild(contentDiv);
        
        chatContainer.appendChild(messageDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function appendLoading() {
        const id = 'loading-' + Date.now();
        const messageDiv = document.createElement('div');
        messageDiv.className = `message assistant`;
        messageDiv.id = id;
        
        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'avatar';
        avatarDiv.textContent = 'AI';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'content';
        contentDiv.innerHTML = `
            <div class="loading-dots">
                <div class="dot"></div>
                <div class="dot"></div>
                <div class="dot"></div>
            </div>
        `;

        messageDiv.appendChild(avatarDiv);
        messageDiv.appendChild(contentDiv);
        
        chatContainer.appendChild(messageDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
        
        return id;
    }

    const modal = document.getElementById('chunk-modal');
    const modalBody = document.getElementById('modal-body');
    const closeModalBtn = document.getElementById('close-modal-btn');

    if (closeModalBtn) {
        closeModalBtn.addEventListener('click', () => {
            modal.classList.add('hidden');
        });
    }

    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.add('hidden');
        }
    });

    async function openModal(chunkId) {
        modal.classList.remove('hidden');
        modalBody.innerHTML = 'Lade...';
        try {
            const res = await fetch(`/api/chunk/${chunkId}`);
            const data = await res.json();
            
            if (data.error) {
                modalBody.innerHTML = `<div style="color: red;">${data.error}</div>`;
                return;
            }

            const sourceText = data.source_file ? ` (${data.source_file})` : '';
            
            modalBody.innerHTML = `
                <h2 style="color: #ffffff; margin-top: 0; margin-bottom: 5px;">${data.title}</h2>
                <div style="color: #cccccc; margin-bottom: 20px; font-size: 0.9em;">${data.type}${sourceText}</div>
                <div style="color: #ffffff; line-height: 1.5; white-space: pre-wrap;">${data.content}</div>
            `;
        } catch (e) {
            modalBody.textContent = 'Fehler beim Laden des Chunks.';
            console.error(e);
        }
    }
});
