import colorsys
import math
import fitz
import os
import re
from tqdm import tqdm
from collections import Counter
import copy

# class ConnectedComponent:
#     def __init__(self, nodes=[]):
#         self.nodes = nodes
#         self.calculate_bbox()
#         self.bbox = Bbox(self.min_x, self.min_y, self.max_x - self.min_x, self.max_y - self.min_y)

#     def calculate_bbox(self):
#         self.min_x, self.min_y = float('inf'), float('inf')
#         self.max_x, self.max_y = -float('inf'), -float('inf')

#         for node in self.nodes:
#             self.min_x = min(self.min_x, node.bbox.x)
#             self.min_y = min(self.min_y, node.bbox.y)
#             self.max_x = max(self.max_x, node.bbox.x + node.bbox.w)
#             self.max_y = max(self.max_y, node.bbox.y + node.bbox.h)

#     def draw_bbox(self, img_bgr):
#         cv2.rectangle(img_bgr, (self.min_x, self.min_y), (self.max_x, self.max_y), (0, 0, 0, 0.5), 1)

# class Bbox:
#     def __init__(self, x, y, w, h):
#         self.x = x
#         self.y = y
#         self.w = w
#         self.h = h

#     def distance_to(self, bbox):
#         x1, y1, w1, h1 = self.x, self.y, self.w, self.h
#         x2, y2, w2, h2 = bbox.x, bbox.y, bbox.w, bbox.h
        
#         left1, right1, bottom1, top1 = x1, x1 + w1, y1, y1 + h1
#         left2, right2, bottom2, top2 = x2, x2 + w2, y2, y2 + h2
        
#         if right1 >= left2 and left1 <= right2 and top1 >= bottom2 and bottom1 <= top2:
#             return 0.0
        
#         horizontal_distance = max(left2 - right1, left1 - right2, 0)
#         vertical_distance = max(bottom2 - top1, bottom1 - top2, 0)
        
#         if horizontal_distance > 0 and vertical_distance == 0:
#             return horizontal_distance
#         if vertical_distance > 0 and horizontal_distance == 0:
#             return vertical_distance
        
#         return (horizontal_distance ** 2 + 4 * vertical_distance ** 2) ** 0.5
    

# class Node:
#     def __init__(self, index, bbox):
#         self.index = index
#         self.bbox = bbox
#         self.neighbours = []


class MatchingTool:
    def __init__(self, pdf_data, latex_data, folder_path, par_combination):
        self.pdf_data = pdf_data
        self.par_combination = par_combination
        self.pdf_data.calculate_context(self.par_combination['context_words'])
        self.latex_data = latex_data
        self.folder_path = folder_path

        self.siblings_offset = par_combination['siblings_offset']
        self.cousins_offset = par_combination['cousins_offset']
        self.equation_dist_threshold = par_combination['equation_dist_threshold']
        self.lcs_max_distance = par_combination['lcs_max_distance']
        self.num_nearest_lines = par_combination['num_nearest_lines']
        self.num_nearest_blocks = par_combination['num_nearest_blocks']

    def perform_matching(self):
        pdf_lines = copy.deepcopy(self.pdf_data.elements['text_boxes'])
        tex_lines = copy.deepcopy(self.latex_data.get_leaves())

        # self.mark_pdf('pdf_processing')

        for step in tqdm(self.par_combination['operations'], desc=f'- LaTeX-PDF matching: ', leave=False):
            if step[0] == 'accurate':
                self.accurate_match(tex_lines, pdf_lines, step[1], step[2], step[3])
            elif step[0] == 'best_guess':
                self.best_guess_match(tex_lines, pdf_lines, step[1], step[2], step[3])
            elif step[0] == 'equation':
                self.aggregate_equations(tex_lines, pdf_lines)
            elif step[0] == 'leftover':
                self.leftover_match(tex_lines, pdf_lines)

        # self.calculate_remainings(accurate_match_pdf_path)
        return pdf_lines
    
    def bag_of_words_matching_score(self, a, b):
        bag_a = [[char, False] for char in a if char != ' ']
        bag_b = [[char, False] for char in b if char != ' ']
        
        if len(bag_a) == 0 or len(bag_b) == 0:
            return [0, None, None]
        
        union = len(bag_a) + len(bag_b)
        intersection = 0
        for char in bag_a:
            for other in bag_b:
                if char[0] == 'Ỽ':
                    intersection += 2
                    break
                
                if char[0] == other[0] and not other[1]:
                    intersection += 2
                    other[1] = True
                    break

        return [intersection / union, None, None]

    def longest_common_subsequence(self, a1, a2, a3, b):
        # def is_equal(x, y, equation=False):
        #     x = x if equation else x.lower()
        #     y = y if equation else y.lower()

        #     if x == y:
        #         return True

        #     if y.startswith('~\\cite{') and y.endswith('}'):
        #         if x.startswith('[') and x.endswith(']'):
        #             x_numbers = x[1:-1].split(',')
        #             if all(num.strip().isdigit() for num in x_numbers):
        #                 y_citations = y[7:-1].split(',')
        #                 if len(x_numbers) == len(y_citations):
        #                     return True

        #     return False
        
        def split_special(text):
            dollar_pattern = r'\$(.*?)\$'
            dollar_parts = re.findall(dollar_pattern, text)
            outside_parts = re.split(dollar_pattern, text)
            
            result = []
            for part in outside_parts:
                if part in dollar_parts:
                    result.extend(list(part))
                else:
                    result.extend(re.findall(r'\[.*?\]|[\w-]+[^\w\s]*|\S', part))
            
            return result
        
        if len(a2) == 0 or len(b) == 0:
            return [0, None, None]

        a = a1 + a2 + a3

        words_a = re.findall(r'\[.*?\]|[\w−]+[^\w\s]*|\S', a)
        words_a1 = re.findall(r'\[.*?\]|[\w−]+[^\w\s]*|\S', a1)
        words_a12 = re.findall(r'\[.*?\]|[\w−]+[^\w\s]*|\S', a1 + a2)
        words_b = split_special(b)

        m, n = len(words_a), len(words_b)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        pt = [[0] * (n + 1) for _ in range(m + 1)]
        for j in range(1, n + 1):
            pt[0][j] = j - 1
        for i in range(1, m + 1):
            pt[i][0] = i - 1

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if words_a[i - 1].lower() == words_b[j - 1].lower():
                    if i == 1 or j == 1:
                        dp[i][j] = 1
                    else:
                        dp[i][j] = dp[i - 1][j - 1] + math.exp(-pt[i - 1][j - 1] / 2)
                    pt[i][j] = 0
                else:
                    dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
                    if pt[i - 1][j] == 0 or pt[i][j - 1] == 0 or pt[i - 1][j - 1] == 0:
                        pt[i][j] = 1
                    else:
                        pt[i][j] = min(pt[i][j - 1], pt[i - 1][j], pt[i - 1][j - 1]) + 1

        if m == 0 or dp[m][n] / m == 0:
            return [0, None, None] 

        index = len(b)
        start_index, end_index = None, None
        i, j = m, n
        while i > 0 and j > 0 and index > 0:
            index -= b[index - 1] == ' '
            if pt[i][j] == 0:
                if len(words_a1) < i <= len(words_a12):
                    if end_index is None:
                        end_index = min(len(b), index + 1)
                    start_index = max(index - len(words_b[j - 1]), 0)
                i -= 1
                j -= 1
                index -= len(words_b[j])
            elif dp[i - 1][j] > dp[i][j - 1]:
                i -= 1
            else:
                j -= 1
                index -= len(words_b[j])

        if m == 0 or start_index is None or end_index is None or start_index > end_index or abs(end_index - start_index - len(a2)) > self.lcs_max_distance:
            return [0, None, None]

        return [dp[m][n] / m, start_index, end_index]

    # def locality_bonus(self, pdf_lines, pdf_line, tex_line_index):
    #     mult = 1
    #     first = True
    #     parent_block = pdf_line.parent

    #     if parent_block is not None:
    #         distances = [abs(sibling.match_index - tex_line_index) for sibling in parent_block.children if sibling.match_index is not None]
    #         if distances:
    #             mean_distance = sum(distances) / len(distances)
    #             mult *= 1 / (1 + mean_distance ** 2)
    #             first = False

    #     page_siblings = [line for line in pdf_lines if line.page_index == pdf_line.page_index and line.match_index is not None]
    #     if page_siblings:
    #         distances = [abs(sibling.match_index - tex_line_index) for sibling in page_siblings]
    #         mean_distance = sum(distances) / len(distances)
    #         mult *= 1 / (1 + 1 / (40 ** 2) * (mean_distance ** 2))
    #         first = False

    #     return 1 if first else mult

    def find_best_matches(self, pdf_line, tex_lines, max_threshold, difference, skip_equations):
        search_tex_lines = [tex_lines[match[0]] for match in pdf_line.matches]

        if len(search_tex_lines) == 0:
            nearest_lines = []
            offset = self.siblings_offset
            parent_block = pdf_line.parent
            if parent_block is not None:
                for sibling in parent_block.children:
                    if sibling.assigned and sibling is not pdf_line:
                        nearest_lines.append((self.distance(pdf_line, sibling), sibling))
            
            if len(nearest_lines) == 0:
                offset = self.cousins_offset
                nearest_blocks = []
                for block in self.pdf_data.elements['containers']:
                    parent_block = pdf_line.parent
                    if parent_block is not None and block is not None and pdf_line.page_index == block.page_index and block != parent_block:
                            nearest_blocks.append((self.distance(parent_block, block), block))

                nearest_blocks.sort(key=lambda x: x[0])
                nearest_blocks = [block[1] for block in nearest_blocks[:self.num_nearest_blocks]]

                for nearest_block in nearest_blocks:
                    for cousin in nearest_block.children:
                        if cousin.assigned:
                            nearest_lines.append((self.distance(pdf_line, cousin), cousin))

            if len(nearest_lines) == 0:
                range_width = len(tex_lines) * 1
                tex_line_center = pdf_line.page_index / self.pdf_data.num_pages * len(tex_lines)
                start = max(round(tex_line_center - range_width), 0)
                end = min(round(tex_line_center + range_width), len(tex_lines))
                search_tex_lines = tex_lines[start:end]
            else:
                nearest_lines.sort(key=lambda x: x[0])
                nearest_lines = [line[1] for line in nearest_lines[:self.num_nearest_lines]]

                center_index = round(sum(nearest_line.matches[0][0] for nearest_line in nearest_lines) / len(nearest_lines))
                search_tex_lines = tex_lines[max(0, center_index - offset):min(center_index + offset, len(tex_lines))]

        search_tex_lines = [line for line in search_tex_lines if line.content.strip() != '']
        if len(search_tex_lines) == 0:
            return []

        equation_block_types = ['algorithmic', 'equation', 'align', 'gather', 'cases', 'frm', 'table']

        matches = []
        for tex_line in search_tex_lines:
            if pdf_line.equation_hit or any(block_type in tex_line.block_type for block_type in equation_block_types):
                match = self.bag_of_words_matching_score(pdf_line.content, tex_line.leftover)
            else:
                match = self.longest_common_subsequence(pdf_line.prefix, pdf_line.content, pdf_line.suffix, tex_line.leftover)
                if match[1] is None or match[2] is None:
                    continue

            matches.append([tex_line.id, match[0], match[1], match[2]]) 

        if len(matches) == 0:
            return []
        
        matches.sort(reverse=True, key=lambda x: x[1])
        if matches[0][1] < max_threshold:
            return []
        
        equation_block_types = ['algorithmic', 'equation', 'align', 'gather', 'cases', 'frm', 'table']
        if skip_equations and any(block_type in tex_lines[matches[0][0]].block_type for block_type in equation_block_types):
            parent_block = pdf_line.parent
            not_an_equation = False
            if parent_block is not None:
                for sibling in parent_block.children:
                    if sibling.assigned and sibling is not pdf_line and sibling.equation_hit is None:
                        not_an_equation = True
                        break
                    
            if not_an_equation is False:
                pdf_line.equation_hit = tex_lines[matches[0][0]].id
                return []
                
        k = 1
        for k in range(1, len(matches)):
            if matches[0][1] - matches[k][1] > difference:
                break

        return matches[:k]
    
    # def find_equation_lines(self, pdf_lines, tex_lines):
    #     for pdf_line in pdf_lines:
    #         pdf_matches = self.find_best_matches(pdf_line, tex_lines, self.equation_dist_threshold, self.equation_dist_threshold, True)
    
    def assign_match(self, pdf_line, tex_line, skip_equations=False):
        if skip_equations and pdf_line.equation_hit:
            return
        
        # equation_block_types = ['algorithmic', 'equation', 'align', 'gather', 'cases', 'frm', 'table']
        # if skip_equations and any(block_type in tex_line.block_type for block_type in equation_block_types):
        #     pdf_line.equation_hit = tex_line.leftover[pdf_line.matches[0][2]:pdf_line.matches[0][3]]
        #     return
        
        leftover = True if pdf_line.matches[0][2] == None else False
        pdf_line.assigned = True
        if pdf_line.equation_group is not None and isinstance(pdf_line.equation_group, list):
            for equation_line in pdf_line.equation_group:
                equation_line.assigned = True
                equation_line.matches = [[tex_line.id, None, None, None]]

        start = 0 if leftover else pdf_line.matches[0][2]
        end = len(tex_line.leftover) if leftover else pdf_line.matches[0][3]

        tex_line.matches.append({"pdf_id": f"{pdf_line.page_index}.{pdf_line.index}", "matching_string": tex_line.leftover[start:end]})
        tex_line.leftover = tex_line.leftover[:start] + tex_line.leftover[end:]

    def accurate_match(self, tex_lines, pdf_lines, threshold, difference, skip_equations):
        for pdf_line in tqdm(pdf_lines, desc=f"   - accurate / {threshold} / {difference}", leave=False):
            if pdf_line.assigned:
                continue

            pdf_line.matches = self.find_best_matches(pdf_line, tex_lines, threshold, difference, skip_equations)
            
            if len(pdf_line.matches) == 1:
                self.assign_match(pdf_line, tex_lines[pdf_line.matches[0][0]], skip_equations)

    def best_guess_match(self, tex_lines, pdf_lines, threshold, difference, skip_equations):
        for pdf_line in tqdm(pdf_lines, desc=f"   - best guess / {threshold} / {difference}", leave=False):
            if pdf_line.assigned:
                continue

            pdf_line.matches = self.find_best_matches(pdf_line, tex_lines, threshold, difference, skip_equations)
            
            if len(pdf_line.matches) == 0:
                continue

            if len(pdf_line.matches) == 1:
                self.assign_match(pdf_line, tex_lines[pdf_line.matches[0][0]], skip_equations)
                continue

            nearest_lines = []
            parent_block = pdf_line.parent
            if parent_block is not None:
                for sibling in parent_block.children:
                    if sibling.assigned and sibling is not pdf_line:
                        nearest_lines.append((self.distance(pdf_line, sibling), sibling))

            if len(nearest_lines) == 0:
                nearest_blocks = []
                for block in self.pdf_data.elements['containers']:
                    parent_block = pdf_line.parent
                    if parent_block is not None and block is not None and pdf_line.page_index == block.page_index and block != parent_block:
                        nearest_blocks.append((self.distance(parent_block, block), block))

                nearest_blocks.sort(key=lambda x: x[0])
                nearest_blocks = [block[1] for block in nearest_blocks[:self.num_nearest_blocks]]

                for nearest_block in nearest_blocks:
                    for cousin in nearest_block.children:
                        if cousin.assigned:
                            nearest_lines.append((self.distance(pdf_line, cousin), cousin))
                
            nearest_lines.sort(key=lambda x: x[0])
            nearest_lines = [line[1] for line in nearest_lines[:self.num_nearest_lines]]

            if len(nearest_lines) > 0:
                mean_index = sum(nearest_line.matches[0][0] for nearest_line in nearest_lines) / len(nearest_lines)
                pdf_line.matches = [min(pdf_line.matches, key=lambda match: abs(match[0] - mean_index))]
                
                self.assign_match(pdf_line, tex_lines[pdf_line.matches[0][0]], skip_equations)

    def aggregate_equations(self, tex_lines, pdf_lines):
        # equation_pdf_lines = self.find_equation_lines(pdf_lines, tex_lines)
        equation_pdf_lines = [pdf_line for pdf_line in pdf_lines if pdf_line.equation_hit]
        
        for this in equation_pdf_lines:
            for other in equation_pdf_lines:
                if this.page_index == other.page_index and self.distance(this, other) < self.equation_dist_threshold and this.index < other.index:
                    this.eq_neighbours.append(other)
                    other.eq_neighbours.append(this)

        def dfs(node, visited, component):
            stack = [node]
            while stack:
                n = stack.pop()
                if n not in visited:
                    visited.add(n)
                    component.append(n)
                    for neighbour in n.eq_neighbours:
                        if neighbour not in visited:
                            stack.append(neighbour)

        visited = set()
        connected_components = []
        for line in equation_pdf_lines:
            if line not in visited:
                component = []
                dfs(line, visited, component)
                connected_components.append(component)

        for cc in connected_components:
            cc = sorted(cc, key=lambda el: el.element.bbox[0])
            cc[0].equation_group = []
            for i in range(1, len(cc)):
                cc[0].content += cc[i].content
                cc[0].equation_group.append(cc[i])
                bbox_list = list(cc[0].element.bbox)
                bbox_list[0] = min(cc[0].element.bbox[0], cc[i].element.bbox[0])
                bbox_list[1] = min(cc[0].element.bbox[1], cc[i].element.bbox[1])
                bbox_list[2] = max(cc[0].element.bbox[2], cc[i].element.bbox[2])
                bbox_list[3] = max(cc[0].element.bbox[3], cc[i].element.bbox[3])
                cc[0].element.bbox = tuple(bbox_list)
                cc[i].equation_group = cc[0]

    def leftover_match(self, tex_lines, pdf_lines):
        for pdf_line in tqdm(pdf_lines, desc=f"   - leftover", leave=False):
            if not pdf_line.assigned:
                parent_block = pdf_line.parent
                if parent_block is not None:
                    indexes = [sibling.matches[0][0] for sibling in parent_block.children if sibling.assigned and sibling is not pdf_line]
                    if len(indexes) == 0:
                        if len(pdf_line.matches) > 0:
                            pdf_line.assigned = True
                            pdf_line.matches = [pdf_line.matches[0]]
                        continue

                counter = Counter(indexes)
                if len(counter) == 0:
                    continue

                most_common_element, _ = counter.most_common(1)[0]
                pdf_line.matches = [[most_common_element, None, None, None]]
                self.assign_match(pdf_line, tex_lines[pdf_line.matches[0][0]], False)

    def distance(self, a, b):
        x1, y1, w1, h1 = a.element.bbox[0], a.element.bbox[1], a.element.bbox[2] - a.element.bbox[0], a.element.bbox[3] - a.element.bbox[1]
        x2, y2, w2, h2 = b.element.bbox[0], b.element.bbox[1], b.element.bbox[2] - b.element.bbox[0], b.element.bbox[3] - b.element.bbox[1]
        
        left1, right1, bottom1, top1 = x1, x1 + w1, y1, y1 + h1
        left2, right2, bottom2, top2 = x2, x2 + w2, y2, y2 + h2
        
        if right1 >= left2 and left1 <= right2 and top1 >= bottom2 and bottom1 <= top2:
            return 0.0
        
        horizontal_distance = max(left2 - right1, left1 - right2, 0)
        vertical_distance = max(bottom2 - top1, bottom1 - top2, 0)
        
        return (horizontal_distance ** 2 + vertical_distance ** 2) ** 0.5


    # def calculate_remainings(self, pdf_path):
    #     with open(pdf_path, 'rb') as f:
    #         pdf_document_labels = fitz.open(pdf_path)

    #         with open(self.pdf_data.input_file_path, 'rb') as f:
    #             pdf_document_remainings = fitz.open(self.pdf_data.input_file_path)

    #             for element_type in ['text_boxes', 'figures', 'rects', 'components', 'containers']:
    #                 for element in self.pdf_data.elements[element_type]:
    #                     self.clean_document(pdf_document_remainings, element)

    #             remainings_file_path = os.path.join(self.folder_path, 'output', 'remainings.pdf')
    #             pdf_document_remainings.save(remainings_file_path)
    #             pdf_document_remainings.close()
    #             output_folder = os.path.join(self.folder_path, 'output', 'remainings')
    #             os.makedirs(output_folder, exist_ok=True)
    #             images = convert_from_path(remainings_file_path, dpi=300)
                
    #         scale = images[0].width / pdf_document_labels[0].rect.width
    #         for idx, image in enumerate(tqdm(images, desc=f"- find and process remainings")):
    #             connected_components, img_with_cc = self.find_connected_components(image)
    #             for cc in connected_components:
    #                 data = (cc.min_x / scale, cc.min_y / scale, cc.max_x / scale, cc.max_y / scale)
    #                 rect = fitz.Rect(data)
    #                 match_index = self.assign_matching_index(data, idx)
    #                 pdf_document_labels[idx].draw_rect(rect, color=(0, 0, 0, 1))
    #                 # pdf_document_labels[idx].insert_text((data[0] + 3, data[1]), str(match_index), fontsize=10)
    #             img_with_cc.save(os.path.join(output_folder, f'page_{idx + 1}.jpg'))

    #         labeled_file_path = os.path.join(self.folder_path, 'output', 'labeled2.pdf')
    #         pdf_document_labels.save(labeled_file_path)
    #         pdf_document_labels.close()
    #         print('\nArxiv ' + labeled_file_path.split('\\')[1] + ': "' + self.latex_data.content_tree.find_node('doc/tit').content + '" processed and matched with latex')
    #         print('\n' + '-' * 100 + '\n')
    #         webbrowser.open_new_tab(labeled_file_path)

    # def assign_matching_index(self, bbox_data, page_index):
    #     bbox = Bbox(bbox_data[0], bbox_data[1], bbox_data[2], bbox_data[3])
    #     nearest_index = None
    #     min_distance = float('inf')
    #     for el in self.pdf_data.elements['text_boxes']:
    #         if el.page_index == page_index:
    #             other_bbox = Bbox(el.element.bbox[0], el.element.bbox[1], el.element.bbox[2], el.element.bbox[3])
    #             distance = bbox.distance_to(other_bbox)
    #             if distance < min_distance and el.match_index is not None:
    #                 min_distance = distance
    #                 nearest_index = el.match_index

    #     return nearest_index

    # def clean_document(self, pdf_document, el):
    #     if len(el.matches) == 1:
    #         page = pdf_document[el.page_index]
    #         x0, y0, x1, y1 = el.element.bbox
    #         page_height = page.mediabox[3] - page.mediabox[1]
    #         adjusted_y0 = page_height - y1
    #         adjusted_y1 = page_height - y0
    #         bbox = (x0, adjusted_y0, x1, adjusted_y1)
    #         rect = fitz.Rect(bbox)
    #         page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))

    # def find_connected_components(self, image):
    #     img_array = np.array(image)
    #     img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
    #     gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    #     _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    #     num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)

    #     nodes = []
    #     for i in range(1, num_labels):
    #         x, y, w, h, _ = stats[i]
    #         nodes.append(Node(i, Bbox(x, y, w, h)))

    #     distance_threshold = 40
    #     for node in nodes:
    #         for other_node in nodes:
    #             if node.index != other_node.index and node.bbox.distance_to(other_node.bbox) <= distance_threshold:
    #                 node.neighbours.append(other_node)
    #                 other_node.neighbours.append(node)

    #     def dfs(node, visited, component):
    #         stack = [node]
    #         while stack:
    #             n = stack.pop()
    #             if n not in visited:
    #                 visited.add(n)
    #                 component.append(n)
    #                 for neighbour in n.neighbours:
    #                     if neighbour not in visited:
    #                         stack.append(neighbour)

    #     visited = set()
    #     connected_components = []
    #     for node in nodes:
    #         if node not in visited:
    #             component = []
    #             dfs(node, visited, component)
    #             connected_components.append(ConnectedComponent(component))

    #     for cc in connected_components:
    #         cc.draw_bbox(img_bgr)

    #     img_with_rects = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    #     return connected_components, Image.fromarray(img_with_rects)

    def mark_pdf(self, pdf_lines, name):
        with open(self.pdf_data.input_file_path, 'rb') as f:
            pdf_document = fitz.open(self.pdf_data.input_file_path)

            # elements = [
            #     ('text_boxes', (.25, .25, .25, 1)),
            #     ('figures', (.25, .25, 1, 1)),
            #     ('rects', (.25, 0, 0, 1)),
            #     ('components', (.25, 0, .25, 1)),
            #     ('containers', (0, 0, 0, .25)),
            # ] 
            # for element_type, color in elements:
            #     for el in self.pdf_data.elements[element_type]:
            #         self.draw_bounding_box(pdf_document, el, color)

            for pdf_line in pdf_lines:
                if pdf_line.equation_group is None or isinstance(pdf_line.equation_group, list):
                    self.draw_bounding_box(pdf_document, pdf_line, (.25, .25, .25, 1))

            output_file_path = os.path.join(self.folder_path, 'output', name + '.pdf')
            pdf_document.save(output_file_path)
            pdf_document.close()
            return output_file_path

    def draw_bounding_box(self, pdf_document, el, color):
        page = pdf_document[el.page_index]
        x0, y0, x1, y1 = el.element.bbox
        page_height = page.mediabox[3] - page.mediabox[1]
        adjusted_y0 = page_height - y1
        adjusted_y1 = page_height - y0
        bbox = (x0, adjusted_y0, x1, adjusted_y1)
        rect = fitz.Rect(bbox)

        if el.assigned:
            hue = (el.matches[0][0] / 4.35436) % 1 * 360
            saturation = 0.8
            brightness = 0.8
            rgb_color = colorsys.hsv_to_rgb(hue / 360, saturation, brightness)
            color = (rgb_color[0], rgb_color[1], rgb_color[2])

        for i in range(min(3, len(el.matches))):
            page.insert_text((x1 + 3 + 25 * i, adjusted_y1), str(el.matches[i][0]), fontsize=10, color=color)

        if el in self.pdf_data.elements['containers']:
            x, y, width, height = rect
            rect = (x - 1, y - 1, width + 1, height + 1)

        page.draw_rect(rect, color=color)