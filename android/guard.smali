.class public final Lcom/airoha/libfota1562/PairBridgeGuard;
.super Ljava/lang/Object;

.method public static ready(Lcom/airoha/sdk/api/ota/FotaInfo;)Z
    .locals 4
    :try_start
    if-eqz p0, :reject
    invoke-virtual {p0}, Lcom/airoha/sdk/api/ota/FotaInfo;->getFlashSize()Lcom/airoha/sdk/api/ota/FotaInfo$FlashSizeEnum;
    move-result-object v0
    sget-object v1, Lcom/airoha/sdk/api/ota/FotaInfo$FlashSizeEnum;->@FLASH_SIZE@:Lcom/airoha/sdk/api/ota/FotaInfo$FlashSizeEnum;
    if-ne v0, v1, :reject
    const-string v1, "@FIRMWARE_VERSION@"
    invoke-virtual {p0}, Lcom/airoha/sdk/api/ota/FotaInfo;->getFwVersion()Ljava/lang/String;
    move-result-object v0
    invoke-virtual {v1, v0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v0
    if-eqz v0, :reject
    invoke-virtual {p0}, Lcom/airoha/sdk/api/ota/FotaInfo;->getPartnerFwVersion()Ljava/lang/String;
    move-result-object v0
    invoke-virtual {v1, v0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z
    move-result v0
    if-eqz v0, :reject
    invoke-static {}, Lcom/airoha/sdk/AirohaSDK;->getInst()Lcom/airoha/sdk/AirohaSDK;
    move-result-object v0
    invoke-virtual {v0}, Lcom/airoha/sdk/AirohaSDK;->getAirohaFotaControl()Lcom/airoha/sdk/api/ota/AirohaFOTAControl;
    move-result-object v0
    instance-of v1, v0, Lcom/airoha/sdk/AB1562FotaControl;
    if-eqz v1, :reject
    check-cast v0, Lcom/airoha/sdk/AB1562FotaControl;
    invoke-virtual {v0}, Lcom/airoha/sdk/AB1562FotaControl;->getAirohaFotaMgrEx1562()Lcom/airoha/libfota1562/AirohaFotaMgrEx1562;
    move-result-object v0
    if-eqz v0, :reject
    iget v1, v0, Lcom/airoha/libfota1562/Airoha1562FotaMgr;->mAgentFotaState:I
    iget v2, v0, Lcom/airoha/libfota1562/Airoha1562FotaMgr;->mPartnerFotaState:I
    const/16 v3, 0x311
    if-ne v1, v3, :reject
    if-ne v2, v3, :reject
    const-string v0, "PairBridgeGuard"
    const-string v1, "READY: both 0x0311; @FLASH_SIZE@; both @FIRMWARE_VERSION@"
    invoke-static {v0, v1}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I
    const/4 v0, 0x1
    return v0
    :try_end
    .catch Ljava/lang/Exception; {:try_start .. :try_end} :exception
    :exception
    move-exception v0
    :reject
    const-string v0, "PairBridgeGuard"
    const-string v1, "REFUSED: readiness guard failed; no commit requested"
    invoke-static {v0, v1}, Landroid/util/Log;->w(Ljava/lang/String;Ljava/lang/String;)I
    const/4 v0, 0x0
    return v0
.end method
