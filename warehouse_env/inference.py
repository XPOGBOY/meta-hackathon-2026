import os
import json
from openai import OpenAI
from warehouse_env.client import WarehouseEnv
from warehouse_env.models import WarehouseAction

def run_task(task_id: str, env_url: str):
    # Required Hackathon OpenEnv setup hooks
    API_BASE_URL = os.getenv("API_BASE_URL", "https://api.openai.com/v1")
    MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")
    HF_TOKEN = os.getenv("HF_TOKEN")
    LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME")

    # Using actual OpenAI client per the requirements!
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY", HF_TOKEN or "dummy-token"),
        base_url=API_BASE_URL
    )

    print(f"[START]")

    step_count = 0
    final_grader_score = 0.0

    try:
        with WarehouseEnv(base_url=env_url).sync() as env:
            # Pass the task name exactly as defined in openenv.yaml
            result = env.reset(task_name=task_id)
            obs = result.observation
            done = result.done
            
            system_prompt = (
                "You are an automated logistics robot operating in a discrete grid. "
                "Your valid actions are purely integer digits: 0 (Up), 1 (Down), 2 (Left), 3 (Right), 4 (Pick). "
                "Output ONLY one of these single digits representing your next move."
            )

            while not done and step_count < 200:
                prompt = (
                    f"You are navigating. Your pos: {obs.robot_pos}.\n"
                    f"Inventory size: {obs.inventory}. Items left at: {obs.items_left}.\n"
                    f"Obstacles are at: {obs.obstacles}.\n"
                    f"Previous message: {obs.message}\n"
                    f"Action?"
                )
                
                try:
                    response = client.chat.completions.create(
                        model=MODEL_NAME,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.0
                    )
                    txt = response.choices[0].message.content.strip()
                    action_str = ''.join(filter(str.isdigit, txt))
                    action_id = int(action_str[0]) if action_str else 0
                except Exception as e:
                    # print(f"LLM Error: {e}")
                    action_id = 0 # Dummy default if LLM fails (e.g. rate limit)
                    
                try:
                    result = env.step(WarehouseAction(action_id=action_id))
                    obs = result.observation
                    done = result.done
                    # OpenEnv requires we accumulate the reward from the env.
                    # Our environment now outputs 0.0 during steps, and the final 0.0-1.0 grader score upon completion.
                    reward_step = result.reward or 0.0
                    step_count += 1
                    
                    log_entry = {
                        "step": step_count,
                        "action": action_id,
                        "reward": reward_step,
                        "done": done,
                        "robot_pos": list(obs.robot_pos),
                        "inventory": obs.inventory,
                        "message": obs.message,
                    }
                    print(f"[STEP] {json.dumps(log_entry)}")
                    
                    if done:
                        total_items = obs.inventory + len(obs.items_left)
                        final_grader_score = float(obs.inventory) / float(total_items) if total_items > 0 else 0.0
                        break
                except Exception as e:
                    print(f"[ERROR] Step error: {e}")
                    break
    except Exception as e:
        print(f"[ERROR] Environment connection or execution error: {e}")

    print(f"[END] Final Score: {final_grader_score:.4f}, Steps taken: {step_count}\n")

def run_inference():
    # Environment URL defaults
    env_url = os.getenv("OPENENV_BASE_URL", "ws://127.0.0.1:8000")
    env_url = env_url.replace("http://", "ws://").replace("https://", "wss://")
    print(f"[INFO] Using environment URL: {env_url}")
    
    # Run the exact 3 tasks defined in our openenv.yaml
    tasks = ["easy_picking", "medium_picking", "hard_picking"]
    for idx, t in enumerate(tasks):
        print(f"--- Running Task {idx+1}/3: {t} ---")
        try:
            run_task(t, env_url)
        except Exception as e:
            print(f"[ERROR] Unhandled exception in task {t}: {e}")

if __name__ == "__main__":
    try:
        run_inference()
    except Exception as e:
        print(f"[FATAL] run_inference crashed: {e}")
