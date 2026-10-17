# KANR — BEHAVIOR-1K 2026 evaluation README

Team KANR (UT Austin, Independent): Keshav Balakrishna, Abhijay Gangarapu, Nishan Mani, Rithik Satarla.
Method: dev-selected policy bank. Each task is served by exactly one of ten checkpoints, chosen from
development instances only. Report and code: https://policy-bank.vercel.app ·
https://github.com/FungousLand1941/policy-bank

## Self-evaluation

1,000 unchanged metric JSONs (100 tasks × instances 301–310 × one rollout). Mean Q =
**0.15605353674103672**; 37 / 1,000 successes; 71 tasks with nonzero Q. Results come from Isaac Sim 6.0.1
(organizers allowed Isaac 6 for public results; Isaac 5.1 crashed with our cluster's GPU driver), the
`RGBDFullResWrapper` and the R1Pro configuration in this archive. The scorer copy bundled with the
simulator uses a 20-instance denominator and prints 0.07802676837051836 on these files; the published
ten-instance contract gives 0.15605. Two duplicate completed cells were resolved by keeping the first
completed attempt regardless of score (`spraying_for_bugs`/307 kept 0.5, later 0.0;
`cook_brussels_sprouts`/303 kept 0.0, later 0.0). Seven episodes came from a recovery pass with action
replay 0; 716 used replay 32 and 277 replay 20. All are reported unchanged.

## Docker images: one image per policy, one container per task

All images are public on Docker Hub (`docker.io/gnishan123/b1k-submission`). Pull by digest. Start a **fresh container for each
task** on a dedicated GPU (24 GB); the container binds to the first task id it receives and serves one
evaluator connection with batches of 1–10 environments. No restart policy.

| Policy | Tag | Digest | Tasks |
|---|---|---|---|
| `comet@ymetz9999` (ymetz pt50 step 9999) | `docker.io/gnishan123/b1k-submission:kanr-test-cachefix-comet-ymetz9999-20261017` | `sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` | 50, 51, 52, 53, 55, 58, 59, 60, 61, 62, 63, 64, 65, 66, 68, 69, 70, 71, 72, 73, 74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 99 |
| `pt50` (Comet π0.5 pt50) | `docker.io/gnishan123/b1k-submission:kanr-test-cachefix-pt50-20261017` | `sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` | 2, 3, 6, 7, 8, 10, 11, 15, 16, 17, 21, 22, 23, 24, 26, 27, 28, 35, 36, 37, 39, 41, 43, 45, 49 |
| `winner1` (2025 winner ckpt 1) | `docker.io/gnishan123/b1k-submission:kanr-test-cachefix-winner1-20261017` | `sha256:a10e85efdc8fd4a4d695c6f3d6f57043dbafac66c342ba02df297fb73c26f8c7` | 5, 13, 14, 19, 25, 29, 34, 42, 44, 47, 48 |
| `winner2` (2025 winner ckpt 2) | `docker.io/gnishan123/b1k-submission:kanr-test-cachefix-winner2-20261017` | `sha256:22edcf726e20a41237c3015a9b0c16a34956266db46ebdaac764acc478d51550` | 1, 12, 18, 20, 30 |
| `winner3` (2025 winner ckpt 3) | `docker.io/gnishan123/b1k-submission:kanr-test-cachefix-winner3-20261017` | `sha256:755f0af39ac55696b505802fb9b4f219e5ee711b566b8fde5e2379fdf3d0fb6f` | 4, 31, 32, 38, 46 |
| `w100@j_jl_4task100` (JackLiu 4-task specialist) | `docker.io/gnishan123/b1k-submission:kanr-test-cachefix-w100-j_jl_4task100-20261017` | `sha256:d5d27dd7ba4da7cac1abd0c6839a3491461b2f0613848401ab97916648be2d06` | 54, 56, 77, 98 |
| `s150997` (pt50 + 2026 demos (ours)) | `docker.io/gnishan123/b1k-submission:kanr-test-cachefix-s150997-20261017` | `sha256:f7b4fffc18acf4154fd62446a6d823763679c9766adaed81db100a5b48354a80` | 33, 57, 67 |
| `pt12` (Comet π0.5 pt12) | `docker.io/gnishan123/b1k-submission:kanr-test-cachefix-pt12-20261017` | `sha256:a76256c005327fdf06a184365b8338e088cc9e130923401f2226c8a1e3a0b46c` | 0, 9 |
| `w100@b_amy_t90` (amyjia 5-task specialist) | `docker.io/gnishan123/b1k-submission:kanr-test-cachefix-w100-b_amy_t90-20261017` | `sha256:ff50f6f73dc6f99e13fe91b84dffc35feff15d17dca9c6818ca4339c4ebb673f` | 96, 97 |
| `winner4` (2025 winner ckpt 4) | `docker.io/gnishan123/b1k-submission:kanr-test-cachefix-winner4-20261017` | `sha256:bd711c17de64f1b4c06e3f48dc8c290b86d888c88600fd787c542c958d68be1c` | 40 |

```sh
docker pull docker.io/gnishan123/b1k-submission@<digest-for-the-task>
docker run --rm --gpus '"device=0"' -p 8000:8000 docker.io/gnishan123/b1k-submission@<digest-for-the-task>
# wait for: curl -fsS http://127.0.0.1:8000/healthz   ->  OK   (model load takes about 1 minute)
```

Interface: websocket on port 8000 (msgpack-numpy, the BEHAVIOR 2026 policy protocol), proprio (61,)
or (N,61) with N ≤ 10, 23-dimensional actions, **global action chunk 4**
(`--replay-action-chunk-size 4`), `{"reset": True}` resets with no reply. Invalid input, nonfinite
actions or model errors close the connection with 1011 and stop the container (no substitute actions);
a second concurrent connection is refused with 1013. Per-query limit 550 s inside the server.

Example evaluator command (one task; replace task name and output directory):

```sh
python -m omnigibson.eval.eval --task-name turning_on_radio --mode <split> \
  --instance-indices <indices> --num-envs 1 --num-rollouts 1 \
  --policy websocket --host 127.0.0.1 --port 8000 \
  --robot-config robot_config/r1pro.yaml \
  --env-wrapper omnigibson.eval.wrappers.RGBDFullResWrapper \
  --output-dir <new-output-dir> --write-video --headless --replay-action-chunk-size 4
```

## Task → image

| Task | Name | Image |
|---|---|---|
| 0 | turning_on_radio | `docker.io/gnishan123/b1k-submission@sha256:a76256c005327fdf06a184365b8338e088cc9e130923401f2226c8a1e3a0b46c` |
| 1 | picking_up_trash | `docker.io/gnishan123/b1k-submission@sha256:22edcf726e20a41237c3015a9b0c16a34956266db46ebdaac764acc478d51550` |
| 2 | putting_away_Halloween_decorations | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 3 | cleaning_up_plates_and_food | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 4 | can_meat | `docker.io/gnishan123/b1k-submission@sha256:755f0af39ac55696b505802fb9b4f219e5ee711b566b8fde5e2379fdf3d0fb6f` |
| 5 | setting_mousetraps | `docker.io/gnishan123/b1k-submission@sha256:a10e85efdc8fd4a4d695c6f3d6f57043dbafac66c342ba02df297fb73c26f8c7` |
| 6 | hiding_Easter_eggs | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 7 | picking_up_toys | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 8 | rearranging_kitchen_furniture | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 9 | putting_up_Christmas_decorations_inside | `docker.io/gnishan123/b1k-submission@sha256:a76256c005327fdf06a184365b8338e088cc9e130923401f2226c8a1e3a0b46c` |
| 10 | set_up_a_coffee_station_in_your_kitchen | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 11 | putting_dishes_away_after_cleaning | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 12 | preparing_lunch_box | `docker.io/gnishan123/b1k-submission@sha256:22edcf726e20a41237c3015a9b0c16a34956266db46ebdaac764acc478d51550` |
| 13 | loading_the_car | `docker.io/gnishan123/b1k-submission@sha256:a10e85efdc8fd4a4d695c6f3d6f57043dbafac66c342ba02df297fb73c26f8c7` |
| 14 | carrying_in_groceries | `docker.io/gnishan123/b1k-submission@sha256:a10e85efdc8fd4a4d695c6f3d6f57043dbafac66c342ba02df297fb73c26f8c7` |
| 15 | bringing_in_wood | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 16 | moving_boxes_to_storage | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 17 | bringing_water | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 18 | tidying_bedroom | `docker.io/gnishan123/b1k-submission@sha256:22edcf726e20a41237c3015a9b0c16a34956266db46ebdaac764acc478d51550` |
| 19 | outfit_a_basic_toolbox | `docker.io/gnishan123/b1k-submission@sha256:a10e85efdc8fd4a4d695c6f3d6f57043dbafac66c342ba02df297fb73c26f8c7` |
| 20 | sorting_vegetables | `docker.io/gnishan123/b1k-submission@sha256:22edcf726e20a41237c3015a9b0c16a34956266db46ebdaac764acc478d51550` |
| 21 | collecting_childrens_toys | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 22 | putting_shoes_on_rack | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 23 | boxing_books_up_for_storage | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 24 | storing_food | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 25 | clearing_food_from_table_into_fridge | `docker.io/gnishan123/b1k-submission@sha256:a10e85efdc8fd4a4d695c6f3d6f57043dbafac66c342ba02df297fb73c26f8c7` |
| 26 | assembling_gift_baskets | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 27 | sorting_household_items | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 28 | getting_organized_for_work | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 29 | clean_up_your_desk | `docker.io/gnishan123/b1k-submission@sha256:a10e85efdc8fd4a4d695c6f3d6f57043dbafac66c342ba02df297fb73c26f8c7` |
| 30 | setting_the_fire | `docker.io/gnishan123/b1k-submission@sha256:22edcf726e20a41237c3015a9b0c16a34956266db46ebdaac764acc478d51550` |
| 31 | clean_boxing_gloves | `docker.io/gnishan123/b1k-submission@sha256:755f0af39ac55696b505802fb9b4f219e5ee711b566b8fde5e2379fdf3d0fb6f` |
| 32 | wash_a_baseball_cap | `docker.io/gnishan123/b1k-submission@sha256:755f0af39ac55696b505802fb9b4f219e5ee711b566b8fde5e2379fdf3d0fb6f` |
| 33 | wash_dog_toys | `docker.io/gnishan123/b1k-submission@sha256:f7b4fffc18acf4154fd62446a6d823763679c9766adaed81db100a5b48354a80` |
| 34 | hanging_pictures | `docker.io/gnishan123/b1k-submission@sha256:a10e85efdc8fd4a4d695c6f3d6f57043dbafac66c342ba02df297fb73c26f8c7` |
| 35 | attach_a_camera_to_a_tripod | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 36 | clean_a_patio | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 37 | clean_a_trumpet | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 38 | spraying_for_bugs | `docker.io/gnishan123/b1k-submission@sha256:755f0af39ac55696b505802fb9b4f219e5ee711b566b8fde5e2379fdf3d0fb6f` |
| 39 | spraying_fruit_trees | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 40 | make_microwave_popcorn | `docker.io/gnishan123/b1k-submission@sha256:bd711c17de64f1b4c06e3f48dc8c290b86d888c88600fd787c542c958d68be1c` |
| 41 | cook_cabbage | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 42 | chop_an_onion | `docker.io/gnishan123/b1k-submission@sha256:a10e85efdc8fd4a4d695c6f3d6f57043dbafac66c342ba02df297fb73c26f8c7` |
| 43 | slicing_vegetables | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 44 | chopping_wood | `docker.io/gnishan123/b1k-submission@sha256:a10e85efdc8fd4a4d695c6f3d6f57043dbafac66c342ba02df297fb73c26f8c7` |
| 45 | cook_hot_dogs | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 46 | cook_bacon | `docker.io/gnishan123/b1k-submission@sha256:755f0af39ac55696b505802fb9b4f219e5ee711b566b8fde5e2379fdf3d0fb6f` |
| 47 | freeze_pies | `docker.io/gnishan123/b1k-submission@sha256:a10e85efdc8fd4a4d695c6f3d6f57043dbafac66c342ba02df297fb73c26f8c7` |
| 48 | canning_food | `docker.io/gnishan123/b1k-submission@sha256:a10e85efdc8fd4a4d695c6f3d6f57043dbafac66c342ba02df297fb73c26f8c7` |
| 49 | make_pizza | `docker.io/gnishan123/b1k-submission@sha256:b593eed0493db41d96935f0d903eabcb2a61f0a43f71769700837ff1441c54ff` |
| 50 | freeze_fruit | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 51 | cook_a_brisket | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 52 | sorting_bottles_cans_and_paper | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 53 | tidying_living_room | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 54 | putting_away_toys | `docker.io/gnishan123/b1k-submission@sha256:d5d27dd7ba4da7cac1abd0c6839a3491461b2f0613848401ab97916648be2d06` |
| 55 | re_shelving_library_books | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 56 | make_rose_centerpieces | `docker.io/gnishan123/b1k-submission@sha256:d5d27dd7ba4da7cac1abd0c6839a3491461b2f0613848401ab97916648be2d06` |
| 57 | sweeping_garage | `docker.io/gnishan123/b1k-submission@sha256:f7b4fffc18acf4154fd62446a6d823763679c9766adaed81db100a5b48354a80` |
| 58 | stacking_wood | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 59 | organizing_art_supplies | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 60 | scrubbing_bathroom_floor | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 61 | bringing_paper_to_recycling | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 62 | halve_an_egg | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 63 | installing_smoke_detectors | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 64 | setting_the_table | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 65 | unloading_the_car | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 66 | turning_out_all_lights_before_sleep | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 67 | boxing_food_after_dinner | `docker.io/gnishan123/b1k-submission@sha256:f7b4fffc18acf4154fd62446a6d823763679c9766adaed81db100a5b48354a80` |
| 68 | cleaning_up_branches_and_twigs | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 69 | vacuuming_floors | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 70 | thawing_frozen_food | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 71 | clean_your_rusty_garden_tools | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 72 | cook_a_frozen_pie | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 73 | organizing_school_stuff | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 74 | carrying_out_garden_furniture | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 75 | put_together_a_basic_pruning_kit | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 76 | dispose_of_glass | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 77 | installing_a_modem | `docker.io/gnishan123/b1k-submission@sha256:d5d27dd7ba4da7cac1abd0c6839a3491461b2f0613848401ab97916648be2d06` |
| 78 | make_cabinet_doors | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 79 | polishing_shoes | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 80 | clean_up_broken_glass | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 81 | packing_meal_for_delivery | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 82 | store_batteries | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 83 | store_honey | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 84 | tidying_bathroom | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 85 | putting_dirty_dishes_in_sink | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 86 | make_gift_bags_for_baby_showers | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 87 | collecting_aluminum_cans | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 88 | rearrange_your_room | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 89 | installing_a_fax_machine | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 90 | composting_waste | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 91 | store_produce | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 92 | installing_a_scanner | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 93 | clean_a_keyboard | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 94 | dispose_of_batteries | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 95 | cook_brussels_sprouts | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |
| 96 | cook_broccolini | `docker.io/gnishan123/b1k-submission@sha256:ff50f6f73dc6f99e13fe91b84dffc35feff15d17dca9c6818ca4339c4ebb673f` |
| 97 | setup_a_bar_for_a_cocktail_party | `docker.io/gnishan123/b1k-submission@sha256:ff50f6f73dc6f99e13fe91b84dffc35feff15d17dca9c6818ca4339c4ebb673f` |
| 98 | laying_tile_floors | `docker.io/gnishan123/b1k-submission@sha256:d5d27dd7ba4da7cac1abd0c6839a3491461b2f0613848401ab97916648be2d06` |
| 99 | sorting_books_on_shelf | `docker.io/gnishan123/b1k-submission@sha256:e1892e6a09e90e73ea25fafe94e101c0ec792e8baebfafa0d5fb59bcc8275d43` |

## Status and limits (stated plainly)

- All ten images passed startup, warm-up and synthetic-input batch-1 / batch-10 protocol tests on an
  RTX 3090 as an unprivileged user (longest batch-10 query 3.38 s, sampled GPU memory below 9 GB).
  They have **not** been run through full Isaac Sim 5.1 episodes at 1 FPS on the organizers' GPU class.
  A stricter isolation test (restricted writes and outbound network) failed with CUDA reporting no GPU;
  the cause (test harness or image) is not established.
- Each image currently contains the shared base layers with all ten checkpoints (~135 GB on disk).
- Checkpoints are public models credited to their authors (Team Comet, Ilia Larchenko / Gleb Zarin /
  Akash Karnatak, ymetz, JackLiu0406, amyjia1212; OpenPI / PaliGemma lineage). The Comet weights and the
  amyjia specialist carry no explicit weight licence from their publishers.
