# Voice Search Implementation Guide

This guide outlines the best ways to implement voice-based searching in your Supply Chain Management system, focusing on "free" services.

## Overview

There are two main approaches to implementing voice search:

1.  **Client-Side Processing (Recommended):** The browser or mobile app converts speech to text using native APIs (Web Speech API). The backend receives a standard text search query.
2.  **Server-Side Processing:** The client uploads an audio file. The backend converts it to text using a library and then performs the search.

## Approach 1: Client-Side (Best for "Free" & Performance)

This is the **best way** because:
*   **Cost:** It uses the user's device capabilities (Google/Apple/Microsoft servers via the browser), so it costs you nothing.
*   **Performance:** It's faster as there's no need to upload large audio files.
*   **Simplicity:** Your backend doesn't need to change. You just use your existing search endpoints.

### Implementation Steps

1.  **Frontend (JavaScript):** Use the Web Speech API.

```javascript
// Check browser support
if ('webkitSpeechRecognition' in window) {
  const recognition = new webkitSpeechRecognition();
  recognition.continuous = false;
  recognition.lang = 'en-US'; // or 'ne-NP' for Nepali if supported

  recognition.onresult = function(event) {
    const transcript = event.results[0][0].transcript;
    console.log('Voice query:', transcript);
    
    // Send this text to your existing backend search API
    // Example: GET /api/market/products/?search=${transcript}
    performSearch(transcript);
  };

  recognition.start();
} else {
  alert("Voice search is not supported in this browser.");
}
```

2.  **Backend:** No changes needed! Use your existing `MarketplaceProductFilter`.

## Approach 2: Server-Side (Python Backend)

If you must handle audio on the backend (e.g., for specific device support), you can use the `SpeechRecognition` library which provides a free wrapper around the Google Speech API (for low volume/testing).

### Prerequisites

You will need to install the following packages:
```bash
pip install SpeechRecognition
```

### Implementation

I have created a new module `market/voice_search.py` and updated `market/urls.py` to support this.

#### 1. The Voice Search View (`market/voice_search.py`)

This view accepts an audio file (WAV format recommended), converts it to text, and returns the search results.

#### 2. API Usage

**Endpoint:** `POST /api/market/voice-search/`

**Body:** `form-data` with key `audio_file` containing the recorded audio.

**Response:**
```json
{
    "query": "red apples",
    "results": [ ... product list ... ]
}
```

## Recommendation

**Stick to Approach 1 (Client-Side)** for the best user experience and zero server overhead. Use Approach 2 only if you have a specific requirement to process audio on the server.
