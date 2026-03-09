import asyncio
import aiohttp
import base64
import json

async def main():
    print("--- DEBUG OLLAMA API ---")
    img_path = "import/LM358_pinout.png"
    question = "What is Pin 8 of the LM358?"
    
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode('utf-8')
    
    payload = {
        "model": "moondream",
        "prompt": question,
        "images": [img_b64],
        "stream": False
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post("http://localhost:11434/api/generate", json=payload) as resp:
            data = await resp.json()
            print("\nFull JSON response:")
            print(json.dumps(data, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
