.method public static pairBridgeReady(Lcom/airoha/utapp/sdk/TwsFota1562Fragment;)Z
    .locals 1
    iget-object v0, p0, Lcom/airoha/utapp/sdk/TwsFota1562Fragment;->mFotaInfo:Lcom/airoha/sdk/api/ota/FotaInfo;
    invoke-static {v0}, Lcom/airoha/libfota1562/PairBridgeGuard;->ready(Lcom/airoha/sdk/api/ota/FotaInfo;)Z
    move-result v0
    return v0
.end method

.method public static pairBridgeRefresh(Lcom/airoha/utapp/sdk/TwsFota1562Fragment;)V
    .locals 3
    invoke-static {p0}, Lcom/airoha/utapp/sdk/TwsFota1562Fragment;->pairBridgeReady(Lcom/airoha/utapp/sdk/TwsFota1562Fragment;)Z
    move-result v0
    iget-object v1, p0, Lcom/airoha/utapp/sdk/TwsFota1562Fragment;->mBtn_Commit:Landroid/widget/Button;
    const/4 v2, 0x0
    invoke-virtual {v1, v2}, Landroid/widget/Button;->setVisibility(I)V
    const-string v2, "PairBridge Commit (checked)"
    invoke-virtual {v1, v2}, Landroid/widget/Button;->setText(Ljava/lang/CharSequence;)V
    invoke-virtual {v1, v0}, Landroid/widget/Button;->setEnabled(Z)V
    return-void
.end method
