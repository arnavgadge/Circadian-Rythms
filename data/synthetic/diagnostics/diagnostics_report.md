# CircadianIQ Synthetic Data -- Distribution Diagnostics

Generated at: 2026-09-09T12:27:59.533555+00:00
Seed: 42 | Participants: 12 | Days: 30

## Chronotype proportions
chronotype
intermediate    0.583
early           0.250
late            0.167

## Personality proportions
personality_key
social_jetlag_student     0.250
chaotic_sleeper           0.167
healthy_stable_routine    0.167
screen_heavy_user         0.167
late_eater                0.083
consistent_night_owl      0.083
consistent_early_bird     0.083

## Intrinsic DLMO distribution (hours) by chronotype
(circular mean/std; min/median/max shown midnight-shifted, so >=24 means past midnight)
              count  circular_mean_hour  circular_std_hours  shifted_min  shifted_median  shifted_max
early           3.0               19.46                1.10        18.02           19.65        20.69
intermediate    7.0               21.50                0.13        21.25           21.52        21.67
late            2.0               23.24                0.11        23.13           23.24        23.35

## Final current DLMO distribution (hours, circular)
count                 12.00
circular_mean_hour    22.74
circular_std_hours     1.57
shifted_min           19.28
shifted_median        22.98
shifted_max           25.25

## DLMO change over 30 days (final current vs. initial current, circular difference, hours)
count    12.00
mean      1.45
std       0.82
min      -0.27
25%       1.01
50%       1.93
75%       2.05
max       2.16

## Sleep duration distribution (hours)
count    360.00
mean       7.37
std        0.77
min        4.21
25%        6.94
50%        7.45
75%        7.82
max       10.04

## Evening screen duration distribution (hours) by personality
personality_key
chaotic_sleeper           1.99
consistent_early_bird     0.97
consistent_night_owl      2.94
healthy_stable_routine    1.18
late_eater                1.64
screen_heavy_user         4.05
social_jetlag_student     2.10

## Morning light duration distribution (minutes) by personality
personality_key
chaotic_sleeper           17.3
consistent_early_bird     37.9
consistent_night_owl       8.3
healthy_stable_routine    30.5
late_eater                18.4
screen_heavy_user         18.3
social_jetlag_student     14.6

## Last meal time distribution (mean hour, shifted so post-midnight > 24) by personality
personality_key
chaotic_sleeper           21.40
consistent_early_bird     18.80
consistent_night_owl      23.55
healthy_stable_routine    20.94
late_eater                21.85
screen_heavy_user         22.62
social_jetlag_student     21.07

## Exercise timing distribution (mean hour) by personality
personality_key
chaotic_sleeper           15.68
consistent_early_bird      6.93
consistent_night_owl      18.95
healthy_stable_routine     7.48
late_eater                17.07
screen_heavy_user         18.02
social_jetlag_student     17.22

## Caffeine distribution (mean amount mg, mean hour) by personality
                        caffeine_amount_mg  caffeine_hour
personality_key                                          
chaotic_sleeper                      97.56          11.56
consistent_early_bird                81.15           8.24
consistent_night_owl                140.19          12.54
healthy_stable_routine               87.15           8.52
late_eater                           95.71          10.84
screen_heavy_user                    98.17          10.76
social_jetlag_student               107.99          10.91

## Social jetlag distribution (minutes, free days only) by personality
                        count    mean    std     min     25%     50%     75%     max
personality_key                                                                     
chaotic_sleeper          16.0   91.24  57.17   10.13   50.28   83.44  124.81  218.40
consistent_early_bird     8.0   21.01  15.28    2.56   11.40   18.07   28.09   47.76
consistent_night_owl      8.0   30.34  18.54   10.06   13.88   28.55   39.95   57.45
healthy_stable_routine   16.0   15.86   9.39    2.69    7.99   15.05   23.09   31.22
late_eater                8.0   22.67  12.80    9.08   14.54   19.58   25.91   43.98
screen_heavy_user        16.0   57.64  30.72   15.87   36.24   55.15   76.85  115.82
social_jetlag_student    24.0  204.43  34.45  132.44  182.82  206.45  228.91  280.74
