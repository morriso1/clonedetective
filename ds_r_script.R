library(cowplot)
library(limma)
library(multcomp)
library(tidyverse)
library(broom)
library(ggsignif)
options(digits = 3)

# count data analysis ----
count_df <-
  read_csv("../../my_python_packages/py_clone_detective/data/example_results.csv")

count_df <- count_df %>%
  mutate(across(where(is_character), as_factor)) %>%
  filter(int_img_ch == 'C1') %>%
  dplyr::select(matches("clone$|_pos$|int_img")) %>%
  group_by(int_img, GFP_clone) %>%
  summarise(
    EC = sum(EC_pos),
    ECEE = sum(ECEE_pos),
    preEC = sum(preEC_pos),
    EE = sum(EE_pos),
    ISCorEB = sum(ISCorEB_pos)
  ) %>%
  mutate(
    clone_status = as.factor(if_else(GFP_clone == 0, 'OC', 'IC')),
    genotype = as.factor(if_else(str_detect(int_img, 'a1'), 'ctrl', 'mut')),
    total = EC + ECEE + preEC + EE + ISCorEB
  )

count_df_tidy <-
  count_df %>% pivot_longer(cols = EC:ISCorEB,
                            names_to = 'cell_type',
                            values_to = 'cell_num') %>%
  mutate(cell_type = factor(cell_type, levels = c('ECEE', 'EE', 'EC', 'preEC', 'ISCorEB')))

count_df_tidy_inside <-
  count_df_tidy %>% filter(clone_status == 'IC')

stacked_bar_mean <- count_df_tidy_inside %>%
  filter(clone_status == 'IC') %>%
  ggplot(aes(fill = cell_type, y = cell_num, x = genotype)) +
  geom_bar(position = "stack",
           stat = "summary",
           fun = 'mean') +
  theme_bw() +
  scale_fill_manual(values = c("#000000", "#95a5a6", "#F57171", "#539DC2", "#008b68"))

options(repr.plot.width = 3, repr.plot.height = 3)
theme_set(theme_cowplot(font_size = 14))

glm(total ~ genotype, count_df, family = 'poisson') %>% tidy()

#  proportion data analysis ----

options(repr.plot.width = 3, repr.plot.height = 4)
theme_set(theme_cowplot(font_size = 14))

prop_df_tidy <- count_df_tidy %>%
  mutate(pro_cell_num = cell_num / total,
         g_cs_ct = as.factor(paste(genotype, clone_status, cell_type, sep = "_")))

stacked_bar_prop <- prop_df_tidy %>%
  ggplot(aes(fill = cell_type, y = pro_cell_num, x = genotype)) +
  geom_bar(position = "fill",
           stat = 'summary',
           fun = 'mean') +
  theme_bw() +
  facet_wrap(vars(clone_status)) +
  scale_fill_manual(values = c(
    "#000000",
    "#95a5a6",
    "#F57171",
    "#539DC2",
    "#008b68",
    "#000000"
  )) +
  theme(legend.position = "none")

stacked_bar_prop

glm(pro_cell_num ~ genotype * clone_status * cell_type,
    prop_df_tidy,
    family = quasibinomial) %>%
  tidy()

contr <- limma::makeContrasts(
  mut_IC_ECEE - ctrl_IC_ECEE,
  mut_IC_EE - ctrl_IC_EE,
  mut_IC_EC - ctrl_IC_EC,
  mut_IC_preEC - ctrl_IC_preEC,
  mut_IC_ISCorEB - ctrl_IC_ISCorEB,
  mut_OC_ECEE - ctrl_OC_ECEE,
  mut_OC_EE - ctrl_OC_EE,
  mut_OC_EC - ctrl_OC_EC,
  mut_OC_preEC - ctrl_OC_preEC,
  mut_OC_ISCorEB - ctrl_OC_ISCorEB,
  mut_OC_ECEE - mut_IC_ECEE,
  mut_OC_EE - mut_IC_EE,
  mut_OC_EC - mut_IC_EC,
  mut_OC_preEC - mut_IC_preEC,
  mut_OC_ISCorEB - mut_IC_ISCorEB,
  levels = levels(prop_df_tidy$g_cs_ct)
)

model <-
  glm(pro_cell_num ~ g_cs_ct, prop_df_tidy, family = quasibinomial)

G <- glht(model, mcp(g_cs_ct = t(contr)))

stat_results <- tidy(G, test = adjusted("BH")) %>%
  mutate(
    sig_anot = case_when(
      adj.p.value < 0.0001 ~ '****',
      adj.p.value < 0.001 ~ '***',
      adj.p.value < 0.01 ~ '**',
      adj.p.value < 0.05 ~ '*',
      adj.p.value < 1 ~ 'ns'
    )
  )

# add stats annotations to plot

stat_pairs <-
  map2(stat_results[1:5, ]$sig_anot, stat_results[6:10, ]$sig_anot, ~ c(.x, .y))

colors <-
  c("#95a5a6",
    "#F57171",
    "#539DC2",
    "#008b68",
    "#000000")

positions <- c(1, 1.04, 1.08, 1.12, 1.16)

sizes <- c(0.5, 0, 0, 0, 0)

stacked_bar_prop <-
  stacked_bar_prop + geom_signif(comparisons = list(c('ctrl', 'mut')))

gr <- ggplot_build(stacked_bar_prop)

pmap(list(stat_pairs, colors, positions, sizes), function(sp, col, pos, siz)
  gr$data[[2]] %>%
    mutate(annotation = ifelse(PANEL == 1, sp[1], sp[2])))
