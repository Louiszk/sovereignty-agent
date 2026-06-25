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
            const rawHtml = marked.parse(content);
            contentDiv.innerHTML = DOMPurify.sanitize(rawHtml);
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
});
