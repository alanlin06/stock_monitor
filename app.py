with tab3:
  col_f, col_s = st.columns(2)
  with col_f:
    st.markdown("### 🌐 外資 Top100 族群集中度")
    st.dataframe(grp_fii_top100, use_container_width=True, hide_index=True)
    with st.expander("查看外資 Top100 個股明細"):
      st.dataframe(
          df_fii_top100, use_container_width=True, hide_index=True
      )
  with col_s:
    st.markdown("### 🎯 投信 Top100 族群集中度")
    st.dataframe(grp_sitc_top100, use_container_width=True, hide_index=True)
    with st.expander("查看投信 Top100 個股明細"):
      st.dataframe(
          df_sitc_top100, use_container_width=True, hide_index=True
      )

  st.markdown("---")
  st.subheader("🔥 雙法人重複族群集中度重算")
  if not df_overlap_top100.empty:
    st.dataframe(df_overlap_top100, use_container_width=True, hide_index=True)
  else:
    st.info("目前外資與投信 Top100 名單中無高度重疊之同一族群。")