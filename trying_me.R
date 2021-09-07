library(cowplot)
library(limma)
library(multcomp)
library(tidyverse)
library(broom)
library(ggsignif)
library(lme4)
library(glmmTMB)


# count data analysis ----
count_df <-
  read_csv("../../my_python_packages/clonedetective/data/example_results.csv")

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
    gut = as_factor(str_extract(int_img, 'g\\d\\d')),
    total = EC + ECEE + preEC + EE + ISCorEB
  ) %>% mutate()

count_df_tidy <-
  count_df %>% pivot_longer(cols = EC:ISCorEB,
                            names_to = 'cell_type',
                            values_to = 'cell_num') %>%
  mutate(cell_type = factor(cell_type, levels = c('ECEE', 'EE', 'EC', 'preEC', 'ISCorEB')))

count_df_tidy_inside <-
  count_df_tidy %>% filter(clone_status == 'IC')

stacked_bar_mean <- count_df_tidy_inside %>%
  ggplot(aes(fill = cell_type, y = cell_num, x = genotype)) +
  geom_bar(position = "stack",
           stat = "summary",
           fun = 'mean') +
  theme_bw() +
  scale_fill_manual(values = c("#000000", "#95a5a6", "#F57171", "#539DC2", "#008b68"))

options(repr.plot.width = 3, repr.plot.height = 3)
theme_set(theme_cowplot(font_size = 14))

m1 <- glm.nb(total ~ genotype * clone_status,
          count_df)

m2 <- glmer.nb(total ~ genotype * clone_status + (genotype |
                                                 gut),
            count_df)


m3 <- glmmTMB(total ~ genotype * clone_status + (genotype |
                                                   gut),
              count_df,
              family = 'truncated_nbinom2')

m4 <- glmmTMB(total ~ genotype * clone_status + (genotype |
                                                   gut),
              count_df,
              family = 'nbinom2')

m5 <- glmmTMB(total ~ genotype * clone_status + (genotype |
                                                   gut),
              count_df,
              family = 'nbinom1')

m1_inside = glm(total ~ genotype,
                count_df %>% filter(clone_status == 'IC'),
                family = 'poisson')

m2_inside <- glmer(total ~ genotype + (genotype | gut),
                   count_df %>% filter(clone_status == 'IC'),
                   family = 'poisson')

m3_inside <- glmmTMB(total ~ genotype + (genotype | gut),
                     count_df %>% filter(clone_status == 'IC'),
                     family = 'truncated_poisson')


overdisp_fun <- function(model) {
  rdf <- df.residual(model)
  rp <- residuals(model, type = "pearson")
  Pearson.chisq <- sum(rp ^ 2)
  prat <- Pearson.chisq / rdf
  pval <- pchisq(Pearson.chisq, df = rdf, lower.tail = FALSE)
  c(
    chisq = Pearson.chisq,
    ratio = prat,
    rdf = rdf,
    p = pval
  )
}

overdisp_fun(m1)
summary(m1)

library(emmeans)

install.packages('glmmTMB')

pairs(emmeans(m5, ~ genotype * clone_status), adjust = 'fdr')

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

ml = glm(pro_cell_num ~ genotype * clone_status * cell_type,
         family = quasibinomial,
         prop_df_tidy)


e_ml <- emmeans(ml, ~ genotype * clone_status * cell_type)

comp_results <- contrast(e_ml, 'pairwise',
                         by = 'cell_type',
                         adjust = 'fdr') %>% tidy()


stat_results <- comp_results %>%
  mutate(
    sig_anot = case_when(
      adj.p.value < 0.0001 ~ '****',
      adj.p.value < 0.001 ~ '***',
      adj.p.value < 0.01 ~ '**',
      adj.p.value < 0.05 ~ '*',
      adj.p.value < 1 ~ 'ns'
    )
  )

stat_results

# add stats annotations to plot

stat_pairs <-
  map2(stat_results[1:5,]$sig_anot, stat_results[6:10,]$sig_anot, ~ c(.x, .y))

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