section_id: client_tree_details

1. "client":  text
2. "date": mm/dd/yyyy
3. "time": hh:mm
4. "address_tree_location": text
5. "tree_number": int
6. "sheet": int
7. "of": int
8. "tree_species": "Unknown"
9. "dbh": int
10. "height": int
11. "crown_spread_dia": int
12. "assessors":text
13. "time_frame": int
14. "tools_used": text



section_id: target_assessment

"targets_number[0]": 

15. "target_number": int

16. "label": text
17. "zone_within_drip_line": checkbox
18. "zone_within_1x_height": checkbox
19. "zone_within_1_5x_height": checkbox
20. "occupancy_rate": int
21. "practical_to_move": checkbox
22. "restriction_practical": checkbox

"targets_number[1]": 

23. "target_number": int
24. "label": text
25. "zone_within_drip_line": checkbox
26. "zone_within_1x_height": checkbox
27. "zone_within_1_5x_height": checkbox
28. "occupancy_rate": int
29. "practical_to_move": checkbox
30. "restriction_practical": checkbox

"targets_number[2]": 

31. "target_number": int
32. "label": text
33. "zone_within_drip_line": checkbox
34. "zone_within_1x_height": checkbox
35. "zone_within_1_5x_height": checkbox
36. "occupancy_rate": int
37. "practical_to_move": checkbox
38. "restriction_practical": checkbox

"targets_number[3]": 

39. "target_number": int
40. "label": text
41. "zone_within_drip_line": checkbox
42. "zone_within_1x_height": checkbox
43. "zone_within_1_5x_height": checkbox
44. "occupancy_rate": int
45. "practical_to_move": checkbox
46. "restriction_practical": checkbox



section_id: site_factors

47. "history_of_failures": text

"site_factors.topography"
48. "flat": checkbox
49. "slope": checkbox
50. "slope_percent": int
51. "aspect": checkbox

"site_factors.site_changes":
52. "none": checkbox
53. "grade_change": checkbox
54. "site_clearing": checkbox
55. "changed_soil_hydrology": checkbox
56. "root_cuts": checkbox
57. "landscape_environment": text

"site_factors.soil_conditions":
58. "limited_volume": checkbox
59. "saturated": checkbox
60. "shallow": checkbox
61. "compacted": checkbox
62. "pavement_over_roots": checkbox
63. "percent": int
64. "describe": text

site_factors
65. "prevailing_wind_direction": text

"site_factors.common_weather"
66. "strong_winds": checkbox
67. "ice": checkbox
68. "snow": checkbox
69. "heavy_rain": checkbox
70. "describe": text

section_id: tree_health_and_species

"tree_health_and_species.vigor"
71. "low": checkbox
72. "normal": checkbox
73. "high": checkbox

"tree_health_and_species.foliage":
74. "none_seasonal": checkbox
75. "none_dead": checkbox
76. "normal_percent": int
77. "chlorotic_percent": int
78. "necrotic_percent": int

79. "tree_health_and_species.pests": text
80. "tree_health_and_species.abiotic": text

"tree_health_and_species.species_failure_profile"
81. "branches": checkbox
82. "trunk": checkbox
83. "roots": checkbox
84. "describe": text

section_id: load_factors
"load_factors.wind_exposure"
85. "protected": checkbox
86. "partial": checkbox
87. "full": checkbox

88. "load_factors.wind_funneling": checkbox
89. "load_factors.wind_funneling_notes": text

"load_factors.relative_crown_size":
90. "small": checkbox
91. "medium": checkbox
92. "large": checkbox

"load_factors.crown_density"
93. "sparse": checkbox
94. "normal": checkbox
95. "dense": checkbox

"load_factors.interior_branches_density": 
96. "few": checkbox
97. "normal": checkbox
98. "dense": checkbox

99. "load_factors.vines_mistletoe_moss_present": checkbox
100. "load_factors.vines_mistletoe_moss_notes": text
101. "load_factors.recent_change_in_load_factors": text

section_id: crown_and_branches
102. "unbalanced_crown": checkbox
103. "lcr_percent": int
104. "cracks": checkbox
105. "cracks_notes": text
106. "lightning_damage": checkbox
107. "dead_twigs": checkbox
108. "dead_twigs_percent": int
109. "dead_twigs_max_dia": int
110. "codominant": checkbox
111. "codominant_notes": text
112. "included_bark": checkbox
113. "broken_hangers_number": int
114. "broken_hangers_max_dia": int
115. "weak_attachments": checkbox
116. "weak_attachments_notes": text
117. "cavity_nest_hole_percent": int
118. "over_extended_branches": checkbox
119. "previous_branch_failures": checkbox
120. "previous_branch_failures_notes": text
121. "similar_branches_present": checkbox
122. "dead_missing_bark": checkbox
123. "cankers_galls_burls": checkbox
124. "sapwood_damage_decay": checkbox

"crown_and_branches.pruning_history"
125. "crown_cleaned": checkbox
126. "thinned" : checkbox
127. "raised" : checkbox
128. "reduced": checkbox
129. "topped": checkbox
130. "lion_tailed": checkbox
134. "flush_cuts": checkbox
135. "other": text

section_id: crown_and_branches
131. "conks": checkbox
132. "heartwood_decay": checkbox
133. "heartwood_decay_notes": text
136. "response_growth": text
137. "main_concerns": text
138. "main_concerns_line_2": text

"crown_and_branches.load_on_defect"
139. "N/A": checkbox
140. "minor": checkbox
141. "moderate": checkbox
142. "significant": checkbox
143. "notes": text

"crown_and_branches.likelihood_of_failure"
144. "improbable": checkbox
145. "possible": checkbox
146. "probable": checkbox
147. "imminent": checkbox
148. "notes": text


section_id: trunk
149. "dead_missing_bark": checkbox
150. "abnormal_bark_texture_color": checkbox
154. "codominant_stems": checkbox
155. "included_bark": checkbox
156. "cracks": checkbox
160. "sapwood_damage_decay": checkbox
161. "cankers_galls_burls": checkbox
162. "sap_ooze": checkbox
166. "lightning_damage": checkbox
167. "heartwood_decay": checkbox
168. "conks_mushrooms": checkbox
172. "cavity_nest_hole_percent": int
173. "cavity_nest_hole_depth": int
174. "poor_taper": checkbox
177. "lean_degrees": int
178. "lean_corrected": text
179. "response_growth": text
181. "main_concerns": text
183. "main_concerns_2": text

"trunk.load_on_defect"
185. "N/A": checkbox
186. "minor": checkbox
187. "moderate": checkbox
188. "significant": checkbox

"trunk.likelihood_of_failure"
193. "improbable": checkbox
194. "possible": checkbox
195. "probable": checkbox
196. "imminent": checkbox  


section_id: roots_and_root_collar
151. "collar_buried_not_visible": checkbox
152. "collar_depth": int
153. "stem_girdling": checkbox
157. "dead": checkbox
158. "decay": checkbox
159. "conks_mushrooms": checkbox
163. "ooze": checkbox
164. "cavity": checkbox
165. "cavity_percent": int
169. "cracks": checkbox
170. "cut_damaged_roots": checkbox
171. "distance_from_trunk": int
175. "root_plate_lifting": checkbox
176. "soil_weakness": checkbox
180. "response_growth": text
182. "main_concerns": text
184. "main_concerns_2": text


"roots_and_root_collar.load_on_defect"   
189. "N/A": checkbox
190. "minor": checkbox
191. "moderate": checkbox
192. "significant": checkbox
                         
"roots_and_root_collar.likelihood_of_failure"
197. "improbable": checkbox
198. "possible": checkbox
199. "probable": checkbox
200. "imminent": checkbox
